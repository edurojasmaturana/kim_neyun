"""Fixtures compartidas de la suite de backend.

Estrategia (sin tocar AWS ni Postgres reales):
- Usuarios/auth -> SQLite en memoria, con override de la dependencia get_session.
- DynamoDB      -> moto (mock_aws), con la caché lru de shared.db reseteada.
"""

import os

# Credenciales y región falsas ANTES de importar boto3/moto, para que ningún
# test pueda salir a AWS de verdad. JWT_SECRET usa el default de desarrollo.
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_REGION", "us-east-1")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.users_db import Base, User
from api import auth


@pytest.fixture
def db_sessionmaker():
    """SQLite en memoria con el esquema de `users` creado.

    StaticPool reutiliza una única conexión, de modo que la BD en memoria
    persiste y se comparte entre el hilo del test y el hilo del TestClient.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def session(db_sessionmaker):
    s = db_sessionmaker()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def make_user():
    """Factory de usuarios con la contraseña ya hasheada."""
    def _make(email="user@kim-neyun.cl", password="password123",
              full_name="Usuario", role="viewer", is_active=True):
        return User(
            email=email.lower(),
            password_hash=auth.hash_password(password),
            full_name=full_name,
            role=role,
            is_active=is_active,
        )
    return _make
