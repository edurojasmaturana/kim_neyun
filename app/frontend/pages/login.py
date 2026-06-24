
"""
KIM-NEYÜN — Pantalla de Inicio de Sesión
"""

import streamlit as st
import requests
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PAGE_CONFIG, LOGIN_ENDPOINT

# -----------------------------------------------------------------------------
# CONFIGURACIÓN
# -----------------------------------------------------------------------------

LOGIN_CONFIG = PAGE_CONFIG.copy()
LOGIN_CONFIG["layout"] = "centered"
LOGIN_CONFIG["initial_sidebar_state"] = "collapsed"

st.set_page_config(**LOGIN_CONFIG)

# LOGIN_ENDPOINT ahora viene de config.py (una sola fuente de verdad)

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
    st.switch_page("pages/1_Estimacion_Demanda.py")

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
def authenticate_user(email: str, password: str):
    # Reintentos con backoff: la base de datos es serverless con
    # capacidad minima 0, por lo que la primera peticion tras un
    # periodo de inactividad puede fallar mientras "despierta".
    intentos = 3
    espera_segundos = [2, 4]  # backoff entre reintentos (no en el ultimo intento)

    for intento in range(intentos):
        try:
            if intento > 0:
                st.info(f"Backend iniciando, reintentando... ({intento + 1}/{intentos})")

            response = requests.post(
                LOGIN_ENDPOINT,
                data={
                    "username": email,
                    "password": password
                },
                timeout=15
            )

            if response.status_code == 200:
                data = response.json()

                st.session_state.token = data["access_token"]
                st.session_state.user_email = email
                st.session_state.login_error = None

                st.success("✓ Autenticación exitosa. Redirigiendo...")
                st.switch_page("pages/1_Estimacion_Demanda.py")
                return

            elif response.status_code == 401:
                st.session_state.login_error = "Correo o contraseña incorrectos."
                return

            else:
                # 500/502/503 durante el arranque de la BD: reintentar
                if intento < intentos - 1:
                    time.sleep(espera_segundos[intento])
                    continue
                st.session_state.login_error = (
                    f"Error del servidor ({response.status_code}). "
                    "El backend puede estar iniciandose, intenta de nuevo en unos segundos."
                )
                return

        except requests.exceptions.ConnectionError:
            if intento < intentos - 1:
                time.sleep(espera_segundos[intento])
                continue
            st.session_state.login_error = "No se pudo conectar al backend."
            return

        except requests.exceptions.Timeout:
            if intento < intentos - 1:
                time.sleep(espera_segundos[intento])
                continue
            st.session_state.login_error = "Tiempo de espera agotado."
            return

        except Exception as e:
            st.session_state.login_error = str(e)
            return
    
    
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

    if submitted:

        if not email or not password:
            st.session_state.login_error = (
                "Por favor completa todos los campos."
            )
            st.rerun()

        authenticate_user(email, password)
