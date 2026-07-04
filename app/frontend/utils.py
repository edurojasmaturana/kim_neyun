"""
Funciones auxiliares para KIM-NEYÜN
"""

import streamlit as st
from datetime import datetime, date, timedelta


# ─────────────────────────────────────────────────────────────────────────────
# SESIÓN
# ─────────────────────────────────────────────────────────────────────────────

def initialize_session_state():
    """Inicializa variables de sesión con valores por defecto."""
    defaults = {
        "last_refresh": datetime.now(),
        "token":        None,
        "user_email":   None,
        "user_role":    None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def require_auth():
    """
    Verifica que haya un token en sesión; si no, redirige al login.
    Llamar al inicio de toda página protegida.
    """
    if not st.session_state.get("token"):
        st.rerun()


def handle_api_error_and_maybe_logout(error_msg: str) -> bool:
    """
    Si el error de la API indica token expirado/inválido, limpia la sesión
    y redirige al login. Retorna True si manejó el error (y la página debe
    detenerse), False si el caller debe mostrar el error normalmente.
    """
    if error_msg and "Token expirado o inválido" in str(error_msg):
        st.session_state.token = None
        st.session_state.user_email = None
        st.session_state.user_role = None
        st.warning("Tu sesión expiró. Redirigiendo al inicio de sesión...")
        st.rerun()
        return True
    return False


def render_logout_button():
    """Botón de cerrar sesión para la sidebar."""
    if st.button("Cerrar sesión", use_container_width=True):
        st.session_state.token = None
        st.session_state.user_email = None
        st.session_state.user_role = None
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# SEMANA EPIDEMIOLÓGICA (CDC/MINSAL — comienza el domingo)
# ─────────────────────────────────────────────────────────────────────────────

def get_semana_epi(d: date):
    """
    Calcula la semana epidemiológica CDC/MINSAL para una fecha dada.
    A diferencia de isocalendar() (que usa lunes como inicio de semana),
    este criterio usa el domingo, igual que el backend (epiweeks).

    Retorna: (año, semana_epi, domingo_de_inicio)
    """
    dia_semana = d.weekday()  # lunes=0 ... domingo=6
    dias_desde_domingo = (dia_semana + 1) % 7
    domingo = d - timedelta(days=dias_desde_domingo)
    inicio_anio = date(domingo.year, 1, 1)
    primer_domingo = inicio_anio - timedelta(days=(inicio_anio.weekday() + 1) % 7)
    se = ((domingo - primer_domingo).days // 7) + 1
    return domingo.year, se, domingo


# ─────────────────────────────────────────────────────────────────────────────
# TRADUCCIÓN DE CAMPOS DE LA API (usa shared.catalog vía config)
# ─────────────────────────────────────────────────────────────────────────────

def traducir_causa(clave: str, traduccion_causas: dict) -> str:
    """
    Traduce la clave de causa que retorna la API (a veces con prefijo
    'Cause_') al nombre legible del catálogo oficial.
    """
    clave_limpia = clave.replace("Cause_", "")
    return traduccion_causas.get(clave_limpia, clave_limpia.replace("_", " "))


def traducir_edad(clave: str, traduccion_edades: dict) -> str:
    """Traduce la clave de grupo etario al nombre legible del catálogo oficial."""
    return traduccion_edades.get(clave, clave)


# ─────────────────────────────────────────────────────────────────────────────
# FECHAS — límite seguro para los selectores de calendario
# ─────────────────────────────────────────────────────────────────────────────

def fecha_maxima_consultable() -> date:
    """
    El batch de inferencia (run_batch.py) solo precomputa hacia atrás desde
    hoy; nunca calcula semanas futuras. Por eso el selector de fecha no debe
    permitir elegir más allá de hoy, o garantizamos un 404.
    """
    return date.today()
