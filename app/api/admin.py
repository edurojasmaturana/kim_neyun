"""Backoffice de administración (SQLAdmin), montado en `/admin`.

Equivalente a ActiveAdmin para este stack FastAPI + SQLAlchemy: genera el CRUD a
partir de los modelos existentes y se monta sobre la misma app del Lambda API.
Acceso restringido a usuarios con rol `admin` (mismas credenciales que el login
de la plataforma). Cubre dos necesidades:

- **Gestionar usuarios**: activar/desactivar, cambiar rol, editar nombre.
- **Invitar**: generar un enlace de invitación (el invitado fija su contraseña en
  `/invitaciones/aceptar`).

Las contraseñas NO se gestionan desde aquí: el alta de usuarios ocurre por
invitación, así el admin nunca define ni ve contraseñas.
"""

import html

from sqladmin import Admin, BaseView, ModelView, expose
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

from api.auth import verify_password
from api.invitations import create_invitation, invitation_link
from shared import config
from shared.users_db import Invitation, User, get_engine, get_sessionmaker


class AdminAuth(AuthenticationBackend):
    """Login del panel: valida contra la tabla `users` y exige rol admin."""

    async def login(self, request: Request) -> bool:
        form = await request.form()
        email = (form.get("username") or "").strip().lower()
        password = form.get("password") or ""

        session = get_sessionmaker()()
        try:
            user = session.scalar(select(User).where(User.email == email))
        finally:
            session.close()

        if (
            user is not None
            and user.is_active
            and user.role == "admin"
            and verify_password(password, user.password_hash)
        ):
            request.session.update({"admin_email": user.email})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return bool(request.session.get("admin_email"))


class UserAdmin(ModelView, model=User):
    name = "Usuario"
    name_plural = "Usuarios"
    icon = "fa-solid fa-user"
    category = "Gestión"

    column_list = [User.email, User.full_name, User.role, User.is_active, User.created_at]
    column_searchable_list = [User.email]
    column_sortable_list = [User.email, User.role, User.is_active, User.created_at]
    column_default_sort = [(User.created_at, True)]
    column_details_exclude_list = [User.password_hash]

    # El alta es por invitación (el invitado fija su contraseña), así que aquí no
    # se crean usuarios ni se editan contraseñas: solo se gestionan rol/estado.
    can_create = False
    form_columns = [User.full_name, User.role, User.is_active]
    can_delete = True


class InvitationAdmin(ModelView, model=Invitation):
    name = "Invitación"
    name_plural = "Invitaciones"
    icon = "fa-solid fa-envelope-open-text"
    category = "Gestión"

    column_list = [
        Invitation.email,
        Invitation.role,
        Invitation.created_by,
        Invitation.created_at,
        Invitation.expires_at,
        Invitation.accepted_at,
    ]
    column_sortable_list = [Invitation.created_at, Invitation.expires_at]
    column_default_sort = [(Invitation.created_at, True)]

    # Se crean desde la vista "Invitar"; aquí solo se listan y se pueden revocar.
    can_create = False
    can_edit = False
    can_delete = True


class InvitarView(BaseView):
    """Formulario para emitir una invitación y mostrar el enlace para copiar."""

    name = "Invitar"
    icon = "fa-solid fa-paper-plane"
    category = "Gestión"

    @expose("/invitar", methods=["GET", "POST"])
    async def invitar(self, request: Request):
        error = ""
        if request.method == "POST":
            form = await request.form()
            email = (form.get("email") or "").strip().lower()
            role = form.get("role") or "viewer"
            if role not in ("admin", "viewer"):
                error = "Rol inválido."
            elif "@" not in email or "." not in email:
                error = "Email inválido."
            else:
                session = get_sessionmaker()()
                try:
                    # Evita duplicar cuenta ya existente.
                    if session.scalar(select(User).where(User.email == email)):
                        error = "Ya existe un usuario con ese email."
                    else:
                        admin_email = request.session.get("admin_email", "")
                        raw = create_invitation(session, email, role, admin_email)
                        session.commit()
                        link = invitation_link(raw)
                        return HTMLResponse(_result_page(email, role, link))
                finally:
                    session.close()

        return HTMLResponse(_form_page(error))


# --- HTML de la vista "Invitar" ---------------------------------------------
# Páginas autocontenidas (sin plantillas externas) para no acoplar el deploy a
# archivos de template; mantienen el estilo oscuro del resto del panel.

def _shell(title: str, body: str) -> str:
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)}</title>
<style>
  body {{ font-family: system-ui, sans-serif; background:#0f172a; color:#e2e8f0; margin:0; padding:2rem; }}
  .card {{ max-width:520px; margin:2rem auto; background:#1e293b; padding:1.75rem 2rem; border-radius:12px; }}
  h1 {{ font-size:1.2rem; margin:0 0 1rem; }}
  label {{ display:block; font-size:.85rem; margin:.75rem 0 .25rem; color:#94a3b8; }}
  input, select {{ width:100%; box-sizing:border-box; padding:.6rem .7rem; border-radius:8px;
          border:1px solid #334155; background:#0f172a; color:#e2e8f0; font-size:.95rem; }}
  button {{ margin-top:1.25rem; padding:.6rem 1rem; border:0; border-radius:8px;
           background:#38bdf8; color:#0f172a; font-weight:600; cursor:pointer; }}
  a {{ color:#38bdf8; }}
  .err {{ color:#f87171; font-size:.9rem; }}
  .link-box {{ margin-top:1rem; padding:.75rem; background:#0f172a; border:1px solid #334155;
              border-radius:8px; word-break:break-all; font-family:ui-monospace, monospace; font-size:.85rem; }}
  .muted {{ color:#94a3b8; font-size:.85rem; line-height:1.5; }}
</style></head><body><div class="card"><h1>{html.escape(title)}</h1>{body}</div></body></html>"""


def _form_page(error: str) -> str:
    err = f'<p class="err">{html.escape(error)}</p>' if error else ""
    body = f"""{err}
<form method="post" action="invitar">
  <label>Email del invitado</label>
  <input type="email" name="email" required autofocus>
  <label>Rol</label>
  <select name="role">
    <option value="viewer" selected>viewer (solo consulta)</option>
    <option value="admin">admin (gestiona la plataforma)</option>
  </select>
  <button type="submit">Generar invitación</button>
</form>
<p class="muted" style="margin-top:1.25rem">Se generará un enlace de un solo uso que
caduca en {config.INVITATION_TTL_HOURS} horas. Cópialo y compártelo con la persona:
al abrirlo, ella creará su propia contraseña.</p>
<p style="margin-top:1rem"><a href="../invitation/list">Ver invitaciones</a> ·
<a href="../">Volver al panel</a></p>"""
    return _shell("Invitar a la plataforma", body)


def _result_page(email: str, role: str, link: str) -> str:
    body = f"""<p class="muted">Invitación creada para <strong>{html.escape(email)}</strong>
(rol <strong>{html.escape(role)}</strong>). Comparte este enlace
<strong>una sola vez</strong> (no se volverá a mostrar):</p>
<div class="link-box" id="link">{html.escape(link)}</div>
<button type="button" onclick="navigator.clipboard.writeText(document.getElementById('link').innerText)">Copiar enlace</button>
<p style="margin-top:1rem"><a href="invitar">Invitar a otra persona</a> ·
<a href="../">Volver al panel</a></p>"""
    return _shell("Invitación generada", body)


def setup_admin(app) -> Admin:
    """Monta el backoffice en `/admin` sobre la app FastAPI."""
    authentication_backend = AdminAuth(secret_key=config.ADMIN_SESSION_SECRET)
    admin = Admin(
        app,
        engine=get_engine(),
        authentication_backend=authentication_backend,
        title="KIM-NEYÜN · Backoffice",
    )
    admin.add_view(UserAdmin)
    admin.add_view(InvitationAdmin)
    admin.add_view(InvitarView)
    return admin
