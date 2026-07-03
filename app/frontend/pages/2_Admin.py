"""
KIM-NEYUN - Administracion
Solo accesible para usuarios con rol 'admin'.
Permite invitar nuevos usuarios y gestionar los existentes.
"""
import streamlit as st
import requests
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import PAGE_CONFIG, GLOBAL_CSS, APP_NAME, APP_VERSION, BACKEND_URL
from utils import initialize_session_state, render_logout_button

st.set_page_config(**PAGE_CONFIG)
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
initialize_session_state()

# ─────────────────────────────────────────────────────────────────────────────
# PROTECCION — solo admins
# ─────────────────────────────────────────────────────────────────────────────
if not st.session_state.get("token"):
    st.switch_page("pages/login.py")

if st.session_state.get("user_role") != "admin":
    st.error("Acceso restringido. Solo administradores pueden ver esta página.")
    st.stop()

token = st.session_state.get("token")
headers = {"Authorization": f"Bearer {token}"}


def _safe_json(response: requests.Response) -> dict | list | None:
    """Parsea JSON de la respuesta; devuelve None si el body no es JSON válido."""
    try:
        return response.json()
    except Exception:
        return None


def _detail_from_response(response: requests.Response, fallback: str) -> str:
    """Extrae el campo 'detail' de una respuesta JSON de error, con fallback seguro."""
    data = _safe_json(response)
    if isinstance(data, dict):
        return str(data.get("detail", fallback))
    return fallback


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        f'<div style="padding:16px 0 20px 0;border-bottom:1px solid rgba(255,255,255,.12);margin-bottom:20px;">'
        f'<div style="font-size:20px;font-weight:700;color:#fff;">{APP_NAME}</div>'
        f'<div style="font-size:11px;color:rgba(255,255,255,.5);margin-top:3px;">Panel de Administración</div>'
        f'<div style="font-size:10px;color:rgba(255,255,255,.3);margin-top:6px;">v{APP_VERSION}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div style="background:rgba(255,255,255,.1);border-radius:6px;padding:7px 10px;'
        f'margin-bottom:12px;font-size:11px;color:rgba(255,255,255,.8);">'
        f'Sesión: <strong>{st.session_state.get("user_email", "")}</strong>'
        f'<br><span style="font-size:10px;opacity:.7;">Rol: Administrador</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)
    render_logout_button()

# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    f'<div style="background:linear-gradient(135deg,#0369a1 0%,#0ea5e9 100%);'
    f'border-radius:12px;padding:20px 24px;margin-bottom:24px;color:#fff;">'
    f'<div style="font-size:10px;text-transform:uppercase;letter-spacing:.1em;opacity:.65;margin-bottom:5px;">'
    f'Sistema predictivo de demanda asistencial</div>'
    f'<div style="font-size:22px;font-weight:700;">Panel de Administración</div>'
    f'<div style="font-size:12px;opacity:.7;margin-top:3px;">Gestión de usuarios e invitaciones</div>'
    f'</div>',
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN 1 — INVITAR USUARIO
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:16px;font-weight:600;color:#0369a1;margin-bottom:16px;">Invitar nuevo usuario</div>',
    unsafe_allow_html=True,
)

with st.form("form_invitacion", border=True):
    col_email, col_rol = st.columns([3, 1])
    with col_email:
        email_invitado = st.text_input(
            "Correo institucional del invitado",
            placeholder="medico@hospitaltemuco.cl",
        )
    with col_rol:
        rol_invitado = st.selectbox(
            "Rol",
            options=["viewer", "admin"],
            index=0,
            help="viewer: solo puede consultar predicciones. admin: puede gestionar usuarios.",
        )

    enviar = st.form_submit_button("Generar invitación", use_container_width=True, type="primary")

    if enviar:
        if not email_invitado:
            st.error("Ingresa el correo del invitado.")
        else:
            with st.spinner("Generando enlace de invitación..."):
                try:
                    resp = requests.post(
                        f"{BACKEND_URL}/admin/invitar",
                        json={"email": email_invitado, "role": rol_invitado},
                        headers=headers,
                        timeout=30,
                    )
                    # El endpoint devuelve 201 (Created) en éxito
                    if resp.status_code in (200, 201):
                        data = _safe_json(resp)
                        if data is None:
                            st.error(
                                "El servidor respondió de forma inesperada. Reintenta en unos segundos."
                            )
                        else:
                            link = data.get("link", "")
                            st.success(
                                f"Invitación generada para **{email_invitado}** con rol **{rol_invitado}**."
                            )
                            st.markdown(
                                f'<div style="background:#e0f2fe;border:1px solid #0ea5e9;border-radius:8px;'
                                f'padding:14px 16px;margin-top:8px;">'
                                f'<div style="font-size:11px;color:#0369a1;font-weight:600;margin-bottom:6px;'
                                f'text-transform:uppercase;letter-spacing:.05em;">Enlace de invitación</div>'
                                f'<code style="font-size:12px;word-break:break-all;color:#0369a1;">{link}</code>'
                                f'<div style="font-size:11px;color:#5a6b82;margin-top:8px;">'
                                f'Copia este enlace y envíalo al invitado. Caduca en 7 días y es de un solo uso.</div>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )
                            st.code(link, language=None)
                    elif resp.status_code == 401:
                        st.error("Token expirado. Recarga la página e inicia sesión nuevamente.")
                    elif resp.status_code == 403:
                        st.error("Sin permisos para invitar usuarios.")
                    elif resp.status_code == 409:
                        detail = _detail_from_response(resp, "Ya existe un usuario con ese email.")
                        st.error(f"Conflicto: {detail}")
                    else:
                        # Cualquier otro error: extraer detail de JSON si está disponible
                        if resp.status_code in (500, 502, 503, 504):
                            st.error(
                                "El servidor está iniciando. Reintenta en unos segundos."
                            )
                        else:
                            detail = _detail_from_response(resp, f"HTTP {resp.status_code}")
                            st.error(f"Error: {detail}")
                except requests.exceptions.Timeout:
                    st.error("Tiempo de espera agotado. Intenta nuevamente.")
                except requests.exceptions.ConnectionError:
                    st.error("No se pudo conectar al servidor.")
                except Exception as e:
                    st.error(f"Error inesperado: {e}")

st.markdown("<div style='margin-top:32px;'></div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN 2 — GESTIONAR USUARIOS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:16px;font-weight:600;color:#0369a1;margin-bottom:16px;">Gestión de usuarios</div>',
    unsafe_allow_html=True,
)

col_refresh, _ = st.columns([1, 3])
with col_refresh:
    recargar = st.button("Actualizar lista", use_container_width=True)

try:
    resp_users = requests.get(
        f"{BACKEND_URL}/admin/users",
        headers=headers,
        timeout=30,
    )

    if resp_users.status_code == 200:
        usuarios = _safe_json(resp_users)
        if not isinstance(usuarios, list):
            st.error("Respuesta inesperada al cargar usuarios. Recarga la página.")
        elif not usuarios:
            st.info("No hay usuarios registrados aún.")
        else:
            for user in usuarios:
                user_id    = user.get("id")
                user_email = user.get("email", "")
                user_role  = user.get("role", "viewer")
                is_active  = user.get("is_active", True)

                color_estado = "#059669" if is_active else "#e53e3e"
                estado_texto = "Activo" if is_active else "Inactivo"

                with st.container():
                    st.markdown(
                        f'<div style="background:#fff;border:1px solid #dde3ed;border-radius:8px;'
                        f'padding:14px 16px;margin-bottom:10px;">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                        f'<div>'
                        f'<div style="font-size:13px;font-weight:500;color:#0369a1;">{user_email}</div>'
                        f'<div style="font-size:11px;color:#5a6b82;margin-top:2px;">'
                        f'Rol: <strong>{user_role}</strong> &nbsp;·&nbsp; '
                        f'<span style="color:{color_estado};font-weight:500;">{estado_texto}</span>'
                        f'</div>'
                        f'</div>'
                        f'</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    col1, col2, col3 = st.columns([2, 2, 1])

                    with col1:
                        nuevo_rol = st.selectbox(
                            "Rol",
                            options=["viewer", "admin"],
                            index=0 if user_role == "viewer" else 1,
                            key=f"rol_{user_id}",
                            label_visibility="collapsed",
                        )

                    with col2:
                        nuevo_estado = st.selectbox(
                            "Estado",
                            options=["Activo", "Inactivo"],
                            index=0 if is_active else 1,
                            key=f"estado_{user_id}",
                            label_visibility="collapsed",
                        )

                    with col3:
                        if st.button("Guardar", key=f"save_{user_id}", use_container_width=True):
                            try:
                                patch_resp = requests.patch(
                                    f"{BACKEND_URL}/admin/users/{user_id}",
                                    json={
                                        "role": nuevo_rol,
                                        "is_active": nuevo_estado == "Activo",
                                    },
                                    headers=headers,
                                    timeout=30,
                                )
                                if patch_resp.status_code == 200:
                                    st.success(f"Usuario {user_email} actualizado.")
                                    st.rerun()
                                else:
                                    detail = _detail_from_response(
                                        patch_resp, f"HTTP {patch_resp.status_code}"
                                    )
                                    st.error(f"Error: {detail}")
                            except Exception as e:
                                st.error(f"Error inesperado: {e}")

    elif resp_users.status_code == 401:
        st.error("Token expirado. Recarga la página e inicia sesión nuevamente.")
    elif resp_users.status_code == 403:
        st.error("Sin permisos para ver la lista de usuarios.")
    else:
        st.error(f"Error al cargar usuarios: HTTP {resp_users.status_code}")

except requests.exceptions.Timeout:
    st.error("Tiempo de espera agotado cargando la lista de usuarios.")
except requests.exceptions.ConnectionError:
    st.error("No se pudo conectar al servidor.")
except Exception as e:
    st.error(f"Error inesperado: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    f'<div style="margin-top:24px;padding-top:14px;border-top:1px solid #dde3ed;'
    f'font-size:11px;color:#5a6b82;">'
    f'{APP_NAME} v{APP_VERSION} — Panel de Administración</div>',
    unsafe_allow_html=True,
)
