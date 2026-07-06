
"""
KIM-NEYÜN — Pantalla de Inicio de Sesión
"""

import threading
import streamlit as st
import requests
import sys
import os
import time
import importlib.util
from pathlib import Path

frontend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(frontend_dir))

config_path = frontend_dir / "config.py"
spec = importlib.util.spec_from_file_location("frontend_config", config_path)
if spec is None or spec.loader is None:
    raise ImportError(f"No se pudo cargar la configuración desde {config_path}")

config_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config_module)

PAGE_CONFIG = getattr(config_module, "PAGE_CONFIG")
LOGIN_ENDPOINT = getattr(config_module, "LOGIN_ENDPOINT")
HEALTH_DB_ENDPOINT = getattr(
    config_module,
    "HEALTH_DB_ENDPOINT",
    f"{getattr(config_module, 'BACKEND_URL', 'http://localhost:8000')}/health/db",
)

# -----------------------------------------------------------------------------
# CONFIGURACIÓN
# -----------------------------------------------------------------------------

LOGIN_CONFIG = PAGE_CONFIG.copy()
LOGIN_CONFIG["layout"] = "centered"
LOGIN_CONFIG["initial_sidebar_state"] = "collapsed"

st.set_page_config(**LOGIN_CONFIG)

# -----------------------------------------------------------------------------
# SESSION STATE
# -----------------------------------------------------------------------------

if "token" not in st.session_state:
    st.session_state.token = None

if "login_error" not in st.session_state:
    st.session_state.login_error = None

# -----------------------------------------------------------------------------
# REDIRECCIÓN
# -----------------------------------------------------------------------------

if st.session_state.token:
    st.rerun()

# -----------------------------------------------------------------------------
# WARMUP AURORA — fire-and-forget, una vez por sesión
# Dispara GET /health/db en background para precalentar Aurora mientras el
# usuario escribe sus credenciales. No se espera la respuesta.
# -----------------------------------------------------------------------------

def _fire_warmup() -> None:
    try:
        requests.get(HEALTH_DB_ENDPOINT, timeout=35)
    except Exception:
        pass


if not st.session_state.get("_warmup_fired"):
    st.session_state["_warmup_fired"] = True
    threading.Thread(target=_fire_warmup, daemon=True).start()

# -----------------------------------------------------------------------------
# CSS
# -----------------------------------------------------------------------------

st.markdown("""
<style>

/* Ocultar elementos Streamlit */
header {visibility:hidden;}
footer {visibility:hidden;}
[data-testid="stSidebar"] {display:none;}
[data-testid="stToolbar"] {display:none;}

/* Fondo */
.stApp {
    background: linear-gradient(
        135deg,
        #0369a1 0%,
        #7dd3fc 100%
    );
}

/* Contenedor */
.block-container {
    max-width: 500px !important;
    padding-top: 90px !important;
}

/* Card */
[data-testid="stForm"] {
    background: white !important;
    padding: 30px !important;
    border-radius: 16px !important;
    box-shadow: 0 10px 30px rgba(0,0,0,.15) !important;
}

/* Inputs */
.stTextInput input {
    border-radius: 8px !important;
    border: 1px solid #d6dde8 !important;
}

/* Botón */
.stFormSubmitButton button {
    width: 100% !important;
    height: 46px !important;
    border-radius: 8px !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
    background: linear-gradient(
        135deg,
        #0369a1 0%,
        #0ea5e9 100%
    ) !important;
}

</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# AUTENTICACIÓN
# -----------------------------------------------------------------------------

def _safe_json(response: requests.Response) -> dict | None:
    """Parsea JSON de la respuesta; retorna None si el body no es JSON."""
    try:
        return response.json()
    except Exception:
        return None


def authenticate_user(email: str, password: str, status_placeholder) -> bool:
    """Intenta login con reintentos para cubrir el cold start de Aurora (~20-25s).

    Reintentos: 4 intentos, timeout 25s c/u, backoff [5, 10, 15]s.
    Cobertura total: hasta ~75s, más que suficiente para el wake-up de Aurora.
    El warmup fire-and-forget ya debería haber calentado Aurora mientras el
    usuario completaba el formulario, por lo que lo normal es éxito en el primer
    intento.

    Retorna True si el login fue exitoso, False en cualquier caso de error.
    NO llama st.switch_page: el llamador lo hace fuera de cualquier try/except
    para que RerunException de Streamlit se propague correctamente al loop principal.
    """
    intentos = 4
    backoff_s = [5, 10, 15]

    for intento in range(intentos):
        try:
            if intento > 0:
                status_placeholder.info(
                    f"El servidor está iniciando, reintentando... ({intento + 1}/{intentos})"
                )

            response = requests.post(
                LOGIN_ENDPOINT,
                data={"username": email, "password": password},
                timeout=25,
            )

            if response.status_code == 200:
                data = _safe_json(response)
                if data is None:
                    st.session_state.login_error = (
                        "Respuesta inesperada del servidor. Reintenta en unos segundos."
                    )
                    return False

                st.session_state.token = data["access_token"]
                st.session_state.user_email = email
                st.session_state.login_error = None

                try:
                    me_resp = requests.get(
                        LOGIN_ENDPOINT.replace("/auth/login", "/auth/me"),
                        headers={"Authorization": f"Bearer {data['access_token']}"},
                        timeout=15,
                    )
                    if me_resp.status_code == 200:
                        me_data = _safe_json(me_resp)
                        st.session_state.user_role = (
                            me_data.get("role", "viewer") if me_data else "viewer"
                        )
                    else:
                        st.session_state.user_role = "viewer"
                except Exception:
                    st.session_state.user_role = "viewer"

                return True

            elif response.status_code == 401:
                st.session_state.login_error = "Correo o contraseña incorrectos."
                return False

            else:
                # 5xx o respuestas inesperadas: Aurora puede estar iniciando — reintentar
                if intento < intentos - 1:
                    time.sleep(backoff_s[intento])
                    continue
                st.session_state.login_error = (
                    f"Error del servidor ({response.status_code}). "
                    "El backend puede estar iniciándose, intenta de nuevo en unos segundos."
                )
                return False

        except requests.exceptions.Timeout:
            if intento < intentos - 1:
                time.sleep(backoff_s[intento])
                continue
            st.session_state.login_error = "Tiempo de espera agotado. Intenta de nuevo."
            return False

        except requests.exceptions.ConnectionError:
            if intento < intentos - 1:
                time.sleep(backoff_s[intento])
                continue
            st.session_state.login_error = "No se pudo conectar al backend."
            return False

        except Exception as e:
            st.session_state.login_error = f"Error inesperado: {e}"
            return False

    return False


# -----------------------------------------------------------------------------
# LOGO
# -----------------------------------------------------------------------------

st.markdown(
    """
    <h1 style="
        text-align:center;
        color:white;
        margin-bottom:0;
        font-size:42px;
        font-weight:700;
    ">
        KIM-NEYÜN
    </h1>

    <p style="
        text-align:center;
        color:white;
        margin-top:5px;
        margin-bottom:25px;
        font-size:22px;
    ">
        Sistema predictivo de demanda asistencial
    </p>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# ERROR
# -----------------------------------------------------------------------------

if st.session_state.login_error:
    st.error(st.session_state.login_error)

# -----------------------------------------------------------------------------
# CONTENEDOR DE ESTADO — colocado ANTES del form para que los mensajes de
# "reintentando" y "éxito" aparezcan fuera de la card blanca (no dentro del form)
# -----------------------------------------------------------------------------

status_placeholder = st.empty()

# -----------------------------------------------------------------------------
# FORMULARIO
# -----------------------------------------------------------------------------

with st.form("login_form"):
    email = st.text_input(
        "Correo institucional",
        placeholder="director@hospitaltemuco.cl"
    )

    password = st.text_input(
        "Contraseña",
        type="password",
        placeholder="••••••••"
    )

    submitted = st.form_submit_button(
        "Iniciar sesión",
        use_container_width=True
    )

# La autenticación corre FUERA del with-form para que st.info/st.success
# se rendericen en status_placeholder (encima de la card), no dentro del form.
# st.switch_page se llama aquí (no dentro de authenticate_user) para que
# RerunException de Streamlit no quede atrapada por el try/except de la función.
if submitted:
    if not email or not password:
        st.session_state.login_error = "Por favor completa todos los campos."
        st.rerun()
    else:
        if authenticate_user(email, password, status_placeholder):
            status_placeholder.success("✓ Autenticación exitosa. Redirigiendo...")
            st.rerun()
