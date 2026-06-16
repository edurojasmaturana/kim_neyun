"""Crea (idempotente) el usuario administrador inicial.

Lee credenciales del entorno y las inserta si el email no existe todavía. Pensado
para correr una vez tras `alembic upgrade head`, tanto en local como contra Aurora
(usa el mismo engine que la app: Data API en AWS, psycopg2 en local).

Uso (desde la carpeta app/):
    ADMIN_EMAIL=admin@uct.cl ADMIN_PASSWORD='...' python -m scripts.seed_admin
"""

import os
import sys

from sqlalchemy import select

from api.auth import hash_password
from shared.users_db import User, get_sessionmaker


def main() -> int:
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD", "")
    full_name = os.environ.get("ADMIN_FULL_NAME", "Administrador KIM-NEYÜN")

    if not email or not password:
        print("Define ADMIN_EMAIL y ADMIN_PASSWORD.", file=sys.stderr)
        return 2

    session = get_sessionmaker()()
    try:
        if session.scalar(select(User).where(User.email == email)):
            print(f"El usuario admin '{email}' ya existe; nada que hacer.")
            return 0
        session.add(
            User(
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
                role="admin",
            )
        )
        session.commit()
        print(f"Usuario admin '{email}' creado.")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
