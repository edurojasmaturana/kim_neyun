"""Acceso a la base de usuarios (Postgres).

Mismo código en local y en AWS:
- Local: motor `postgresql+psycopg2://` (contenedor Postgres de docker-compose),
  tomado de `USERS_DATABASE_URL`.
- AWS:   motor `postgresql+auroradataapi://` (dialecto sqlalchemy-aurora-data-api),
  que ejecuta vía el Data API de Aurora Serverless v2 usando los ARN del cluster y
  del secreto. Así el Lambda NO necesita entrar a la VPC.

El engine se cachea para reutilizarse entre invocaciones tibias de Lambda
(mismo criterio que `shared/db.py` para DynamoDB).
"""

import datetime
import functools
import logging
import time
import uuid

from sqlalchemy import Boolean, DateTime, String, create_engine, text
# StatementError es la base; cubre también su subclase DBAPIError/OperationalError.
# El Data API levanta el 'resuming' como StatementError pelado (al crear el cursor),
# así que hay que capturar la base, no solo DBAPIError.
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from . import config

logger = logging.getLogger("kim.users_db")

# Con Aurora Serverless v2 escalado a cero (min_capacity = 0), la primera consulta
# tras un periodo de inactividad falla mientras el cluster "despierta": el Data API
# responde DatabaseResumingException, que sin manejo se propaga como un 500. El
# resume tarda unos pocos segundos, así que reintentamos con backoff dentro del
# request (cabe holgado en el timeout de 30 s del Lambda).
_RESUME_RETRIES = 6
_RESUME_BACKOFF_S = 2.0


def _is_resuming_error(exc: BaseException) -> bool:
    """True si la excepción (o su causa) es el 'resuming' de Aurora auto-paused.

    Recorre toda la cadena: la causa encadenada (`__cause__`/`__context__`) y, en
    el caso de SQLAlchemy, la excepción original envuelta en `.orig` (que no queda
    en `__cause__`).
    """
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if "DatabaseResumingException" in type(exc).__name__ or "is resuming" in str(exc):
            return True
        exc = exc.__cause__ or exc.__context__ or getattr(exc, "orig", None)
    return False


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # 'admin' puede dar de alta usuarios; 'viewer' solo consume predicciones.
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.datetime.now(datetime.timezone.utc),
    )


class Invitation(Base):
    """Invitación para dar de alta un usuario sin que el admin fije su contraseña.

    El admin genera la invitación desde el backoffice y comparte el enlace; el
    invitado abre el enlace y crea su propia contraseña. Solo se guarda el
    SHA-256 del token (`token_hash`): el token en claro vive únicamente en el
    enlace. Las invitaciones son de un solo uso (`accepted_at`) y caducan
    (`expires_at`).
    """

    __tablename__ = "invitations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="viewer")
    # SHA-256 hex del token (64 chars). Indexado para resolver el enlace por hash.
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    accepted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Email del admin que la creó (auditoría).
    created_by: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )


@functools.lru_cache(maxsize=1)
def get_engine():
    """Construye el engine según el entorno (Data API en AWS, psycopg2 en local)."""
    if config.AURORA_CLUSTER_ARN and config.AURORA_SECRET_ARN:
        # El dialecto lee la región de boto3 (AWS_REGION) y los ARN de connect_args;
        # la base va en el path de la URL (forma documentada del dialecto).
        return create_engine(
            f"postgresql+auroradataapi://:@/{config.AURORA_DATABASE}",
            connect_args={
                "aurora_cluster_arn": config.AURORA_CLUSTER_ARN,
                "secret_arn": config.AURORA_SECRET_ARN,
            },
            pool_pre_ping=True,
        )
    if not config.USERS_DATABASE_URL:
        raise RuntimeError(
            "Falta configurar la base de usuarios: define USERS_DATABASE_URL (local) "
            "o AURORA_CLUSTER_ARN + AURORA_SECRET_ARN (AWS)."
        )
    return create_engine(config.USERS_DATABASE_URL, pool_pre_ping=True)


@functools.lru_cache(maxsize=1)
def get_sessionmaker():
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def _wait_until_awake(session) -> None:
    """Pega un SELECT 1 reintentando mientras Aurora termina de despertar.

    Paga el coste del resume una sola vez por request; si la base ya está activa,
    es un único SELECT trivial. Solo reintenta el 'resuming'; cualquier otro error
    se propaga sin demora.
    """
    for intento in range(1, _RESUME_RETRIES + 1):
        try:
            session.execute(text("SELECT 1"))
            return
        except StatementError as exc:
            if not _is_resuming_error(exc) or intento == _RESUME_RETRIES:
                raise
            session.rollback()
            logger.warning(
                "Aurora resumiendo (auto-paused); reintento %d/%d en %.0fs",
                intento, _RESUME_RETRIES, _RESUME_BACKOFF_S,
            )
            time.sleep(_RESUME_BACKOFF_S)


def get_session():
    """Dependencia FastAPI: una sesión por request, cerrada al terminar."""
    session = get_sessionmaker()()
    try:
        _wait_until_awake(session)
        yield session
    finally:
        session.close()
