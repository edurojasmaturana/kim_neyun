"""Autenticación de KIM-NEYÜN (propia, sobre Postgres).

- Contraseñas hasheadas con bcrypt (passlib).
- Sesiones por token JWT (HS256) firmado con `JWT_SECRET`.
- `get_current_user` es la dependencia que protege el resto de endpoints.

El login sigue la convención OAuth2 "password" (form-data con `username`/`password`)
para que el botón **Authorize** de Swagger UI funcione directo; `username` es el email.
"""

import datetime
import logging

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared import config
from shared.users_db import User, get_session

logger = logging.getLogger("kim.auth")

router = APIRouter(prefix="/auth", tags=["Auth"])

# tokenUrl relativo: respeta el root_path del stage de API Gateway.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# --- Hashing y tokens --------------------------------------------------------

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user: User) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "iat": now,
        "exp": now + datetime.timedelta(minutes=config.ACCESS_TOKEN_TTL_MIN),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALG)


# --- Modelos de E/S ----------------------------------------------------------

class TokenResp(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResp(BaseModel):
    id: str
    # str (no EmailStr): el email ya fue validado al crear el usuario
    # (CrearUsuarioReq); re-validar acá rompería con 500 para emails
    # legítimos en dominios de uso especial (p.ej. .local, .test en dev/seed).
    email: str
    full_name: str
    role: str
    is_active: bool

    model_config = {"from_attributes": True}


class CrearUsuarioReq(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, description="Mínimo 8 caracteres.")
    full_name: str = ""
    role: str = Field(default="viewer", pattern="^(admin|viewer)$")


# --- Dependencias ------------------------------------------------------------

_credentials_exc = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Credenciales inválidas o expiradas.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> User:
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALG])
        user_id = payload.get("sub")
        if not user_id:
            raise _credentials_exc
    except jwt.PyJWTError:
        raise _credentials_exc

    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise _credentials_exc
    return user


def require_admin(current: User = Depends(get_current_user)) -> User:
    if current.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requiere rol de administrador.",
        )
    return current


# --- Endpoints ---------------------------------------------------------------

@router.post("/login", response_model=TokenResp, summary="Iniciar sesión (obtener JWT)")
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
):
    """Valida email (`username`) + contraseña y devuelve un token Bearer."""
    user = session.scalar(select(User).where(User.email == form.username.lower()))
    if user is None or not user.is_active or not verify_password(form.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResp(access_token=create_access_token(user))


@router.get("/me", response_model=UserResp, summary="Datos del usuario autenticado")
def me(current: User = Depends(get_current_user)):
    return current


@router.post(
    "/users",
    response_model=UserResp,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de usuario (solo admin)",
    responses={
        403: {"description": "Requiere rol admin."},
        409: {"description": "El email ya está registrado."},
    },
)
def crear_usuario(
    datos: CrearUsuarioReq,
    session: Session = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    email = datos.email.lower()
    if session.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El email ya está registrado.")
    user = User(
        email=email,
        password_hash=hash_password(datos.password),
        full_name=datos.full_name,
        role=datos.role,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
