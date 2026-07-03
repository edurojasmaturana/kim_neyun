"""Router JSON del panel de administración (frontend Streamlit 2_Admin.py).

Expone los 3 endpoints que llama pages/2_Admin.py con Bearer JWT:
  POST  /admin/invitar          → crea invitación + envía correo al invitado
  GET   /admin/users            → lista todos los usuarios
  PATCH /admin/users/{user_id}  → actualiza rol y/o estado de un usuario

Todos requieren rol admin (via `require_admin`).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.auth import UserResp, require_admin
from api.email_service import send_invitation_email
from api.invitations import create_invitation, invitation_link
from shared.users_db import User, get_session

router = APIRouter(prefix="/admin", tags=["Admin"])


# --- Modelos de E/S ----------------------------------------------------------

class InvitarReq(BaseModel):
    email: EmailStr
    role: str = Field(default="viewer", pattern="^(admin|viewer)$")


class InvitarResp(BaseModel):
    ok: bool
    email: str
    role: str
    link: str
    email_enviado: bool


class PatchUserReq(BaseModel):
    role: str | None = Field(default=None, pattern="^(admin|viewer)$")
    is_active: bool | None = None


# --- Endpoints ---------------------------------------------------------------

@router.post(
    "/invitar",
    response_model=InvitarResp,
    status_code=status.HTTP_201_CREATED,
    summary="Invitar usuario (solo admin)",
    responses={
        409: {"description": "El email ya está registrado."},
    },
)
def invitar(
    req: InvitarReq,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Crea una invitación de un solo uso y envía un correo al invitado con el
    enlace de activación. Devuelve el link siempre (útil para debug) e indica
    si el correo se envió. El link caduca según `INVITATION_TTL_HOURS`.
    """
    email = req.email.lower()
    if session.scalar(select(User).where(User.email == email)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un usuario con ese email.",
        )

    raw = create_invitation(session, email, req.role, admin.email)
    session.commit()
    link = invitation_link(raw)

    email_enviado = send_invitation_email(
        to_email=email, link=link, role=req.role, invited_by=admin.email
    )

    return InvitarResp(
        ok=True, email=email, role=req.role, link=link, email_enviado=email_enviado
    )


@router.get(
    "/users",
    response_model=list[UserResp],
    summary="Listar usuarios (solo admin)",
)
def listar_usuarios(
    session: Session = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """Devuelve todos los usuarios ordenados por fecha de creación (más nuevos primero)."""
    return list(session.scalars(select(User).order_by(User.created_at.desc())).all())


@router.patch(
    "/users/{user_id}",
    response_model=UserResp,
    summary="Actualizar usuario (solo admin)",
    responses={
        404: {"description": "Usuario no encontrado."},
    },
)
def actualizar_usuario(
    user_id: str,
    req: PatchUserReq,
    session: Session = Depends(get_session),
    _admin: User = Depends(require_admin),
):
    """Actualiza rol y/o estado activo de un usuario. Solo los campos presentes
    en el body se modifican (PATCH semántico)."""
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado."
        )
    if req.role is not None:
        user.role = req.role
    if req.is_active is not None:
        user.is_active = req.is_active
    session.commit()
    session.refresh(user)
    return user
