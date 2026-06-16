"""Invitaciones por enlace (flujo público de aceptación).

El admin genera la invitación desde el backoffice (`/admin`); aquí vive la otra
mitad del flujo: el invitado abre el enlace y **fija su propia contraseña**. Estas
rutas son públicas (no llevan `require_admin`) porque el portador del token aún no
tiene cuenta; la seguridad está en el token (un solo uso, caduca, solo se guarda su
hash).
"""

import datetime
import hashlib
import html
import secrets

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared import config
from shared.users_db import Invitation, User, get_sessionmaker

router = APIRouter(prefix="/invitaciones", tags=["Auth"])

# Reutilizamos la regla de contraseña del alta de usuarios (CrearUsuarioReq).
MIN_PASSWORD_LEN = 8


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def hash_token(raw: str) -> str:
    """SHA-256 hex del token. Solo el hash se persiste; el token va en el enlace."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_invitation(session: Session, email: str, role: str, created_by: str) -> str:
    """Crea una invitación y devuelve el token EN CLARO (se muestra una sola vez).

    No commitea: deja la fila en la sesión para que el llamador controle la
    transacción (el backoffice de SQLAdmin gestiona su propia sesión).
    """
    raw = secrets.token_urlsafe(32)
    inv = Invitation(
        email=email.strip().lower(),
        role=role,
        token_hash=hash_token(raw),
        expires_at=_utcnow() + datetime.timedelta(hours=config.INVITATION_TTL_HOURS),
        created_by=created_by,
    )
    session.add(inv)
    return raw


def invitation_link(raw_token: str) -> str:
    """Enlace completo que el admin comparte con el invitado."""
    return f"{config.ACCEPT_BASE_URL}/invitaciones/aceptar?token={raw_token}"


def _valid_invitation(session: Session, token: str) -> Invitation:
    """Devuelve la invitación si el token es válido; si no, lanza 400/410."""
    if not token:
        raise HTTPException(status_code=400, detail="Falta el token de invitación.")
    inv = session.scalar(
        select(Invitation).where(Invitation.token_hash == hash_token(token))
    )
    if inv is None:
        raise HTTPException(status_code=400, detail="Invitación no válida.")
    if inv.accepted_at is not None:
        raise HTTPException(status_code=410, detail="Esta invitación ya fue utilizada.")
    if inv.expires_at <= _utcnow():
        raise HTTPException(status_code=410, detail="Esta invitación ha caducado.")
    return inv


# --- Páginas HTML mínimas (sin dependencias de frontend) ---------------------

def _page(title: str, body: str, status_code: int = 200) -> HTMLResponse:
    doc = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  body {{ font-family: system-ui, sans-serif; background:#0f172a; color:#e2e8f0;
         display:flex; min-height:100vh; align-items:center; justify-content:center; margin:0; }}
  .card {{ background:#1e293b; padding:2rem 2.25rem; border-radius:12px; width:340px;
          box-shadow:0 10px 30px rgba(0,0,0,.4); }}
  h1 {{ font-size:1.15rem; margin:0 0 1rem; }}
  label {{ display:block; font-size:.85rem; margin:.75rem 0 .25rem; color:#94a3b8; }}
  input {{ width:100%; box-sizing:border-box; padding:.6rem .7rem; border-radius:8px;
          border:1px solid #334155; background:#0f172a; color:#e2e8f0; font-size:.95rem; }}
  button {{ margin-top:1.25rem; width:100%; padding:.65rem; border:0; border-radius:8px;
           background:#38bdf8; color:#0f172a; font-weight:600; font-size:.95rem; cursor:pointer; }}
  .msg {{ font-size:.9rem; line-height:1.4; }}
  .muted {{ color:#94a3b8; font-size:.85rem; }}
</style></head>
<body><div class="card"><h1>KIM-NEYÜN · {html.escape(title)}</h1>{body}</div></body></html>"""
    return HTMLResponse(content=doc, status_code=status_code)


def _accept_form(token: str, email: str, error: str = "") -> str:
    err_html = f'<p class="msg" style="color:#f87171">{html.escape(error)}</p>' if error else ""
    return f"""
{err_html}
<p class="muted">Activa tu cuenta para <strong>{html.escape(email)}</strong> creando una contraseña.</p>
<form method="post" action="aceptar">
  <input type="hidden" name="token" value="{html.escape(token)}">
  <label>Contraseña (mínimo {MIN_PASSWORD_LEN} caracteres)</label>
  <input type="password" name="password" required minlength="{MIN_PASSWORD_LEN}" autofocus>
  <label>Repetir contraseña</label>
  <input type="password" name="password2" required minlength="{MIN_PASSWORD_LEN}">
  <button type="submit">Crear cuenta</button>
</form>"""


@router.get("/aceptar", response_class=HTMLResponse, include_in_schema=False)
def aceptar_form(token: str = ""):
    """Muestra el formulario para que el invitado fije su contraseña."""
    session = get_sessionmaker()()
    try:
        try:
            inv = _valid_invitation(session, token)
        except HTTPException as exc:
            return _page("Invitación", f'<p class="msg">{html.escape(str(exc.detail))}</p>',
                         status_code=exc.status_code)
        return _page("Activar cuenta", _accept_form(token, inv.email))
    finally:
        session.close()


@router.post("/aceptar", response_class=HTMLResponse, include_in_schema=False)
def aceptar_submit(
    token: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
):
    """Valida el token y crea (o activa) el usuario con la contraseña elegida."""
    # Import local para evitar un ciclo de importación con api.auth.
    from api.auth import hash_password

    session = get_sessionmaker()()
    try:
        try:
            inv = _valid_invitation(session, token)
        except HTTPException as exc:
            return _page("Invitación", f'<p class="msg">{html.escape(str(exc.detail))}</p>',
                         status_code=exc.status_code)

        if password != password2:
            return _page("Activar cuenta",
                         _accept_form(token, inv.email, "Las contraseñas no coinciden."),
                         status_code=400)
        if len(password) < MIN_PASSWORD_LEN:
            return _page("Activar cuenta",
                         _accept_form(token, inv.email,
                                      f"La contraseña debe tener al menos {MIN_PASSWORD_LEN} caracteres."),
                         status_code=400)

        existing = session.scalar(select(User).where(User.email == inv.email))
        if existing is not None:
            # El email se registró por otra vía entre la invitación y la aceptación.
            inv.accepted_at = _utcnow()
            session.commit()
            return _page("Activar cuenta",
                         '<p class="msg">Ya existe una cuenta con este email. '
                         'Usa la opción de inicio de sesión.</p>',
                         status_code=409)

        session.add(User(
            email=inv.email,
            password_hash=hash_password(password),
            full_name="",
            role=inv.role,
            is_active=True,
        ))
        inv.accepted_at = _utcnow()
        session.commit()

        return _page("Cuenta creada",
                     f'<p class="msg">¡Listo! Tu cuenta <strong>{html.escape(inv.email)}</strong> '
                     'quedó activa. Ya puedes iniciar sesión en la plataforma.</p>')
    finally:
        session.close()
