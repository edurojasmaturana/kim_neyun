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
import uuid

from sqlalchemy import Boolean, DateTime, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from . import config


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


def get_session():
    """Dependencia FastAPI: una sesión por request, cerrada al terminar."""
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
