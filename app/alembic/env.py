"""Entorno de Alembic.

Reutiliza el engine de la app (shared.users_db.get_engine), por lo que las
migraciones corren igual contra Postgres local (psycopg2) que contra Aurora
Serverless v2 por Data API — sin VPC y sin duplicar configuración.
"""

from logging.config import fileConfig

from alembic import context

from shared.users_db import Base, get_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=str(get_engine().url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = get_engine()
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
