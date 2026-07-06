"""
Configuración global — KIM-NEYÜN Frontend
Importa el catálogo de dominio (hospitales, traducciones) desde shared.catalog
para no duplicar la fuente de verdad que usa el backend.
"""

import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
import sys

# Hace que `shared` (carpeta hermana de `frontend`) sea importable
# sin depender del directorio desde donde se ejecute Streamlit.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.catalog import HOSPITALES, TRADUCCION_CAUSAS, TRADUCCION_EDADES

# ─────────────────────────────────────────────────────────────────────────────
# BACKEND — URL de la API (Lambda + API Gateway)
# ─────────────────────────────────────────────────────────────────────────────
BACKEND_URL = os.getenv(
    "API_BASE_URL",
    "http://localhost:8000",
).rstrip("/")

LOGIN_ENDPOINT      = f"{BACKEND_URL}/auth/login"
ME_ENDPOINT         = f"{BACKEND_URL}/auth/me"
HOSPITALES_ENDPOINT = f"{BACKEND_URL}/hospitales"
PREDICTION_ENDPOINT = f"{BACKEND_URL}/predecir"
PROYECCION_ENDPOINT = f"{BACKEND_URL}/proyeccion_anual"
HEALTH_ENDPOINT     = f"{BACKEND_URL}/health"
HEALTH_DB_ENDPOINT  = f"{BACKEND_URL}/health/db"

# Parámetros de conexión
API_TIMEOUT     = int(os.getenv("KIM_API_TIMEOUT", "15"))   # segundos (cold start de Lambda/Aurora puede ser lento)
API_MAX_RETRIES = int(os.getenv("KIM_API_RETRIES", "3"))    # reintentos — alineado a pages/login.py

# ─────────────────────────────────────────────────────────────────────────────
# STREAMLIT
# ─────────────────────────────────────────────────────────────────────────────
PAGE_CONFIG = {
    "page_title": "KIM-NEYÜN",
    "page_icon":  "🫁",
    "layout":     "wide",
    "initial_sidebar_state": "collapsed",
}

# ─────────────────────────────────────────────────────────────────────────────
# PALETA — celeste cielo (institucional UCTemuco)
# ─────────────────────────────────────────────────────────────────────────────
THEME = {
    "navy":        "#0369a1",   # barra lateral, headers
    "blue":        "#0ea5e9",   # elementos secundarios / acentos
    "blue_light":  "#38bdf8",   # acentos interactivos
    "teal":        "#0d9488",   # indicadores positivos
    "bg":          "#f0f8ff",   # fondo general
    "surface":     "#ffffff",   # tarjetas
    "border":      "#dde3ed",   # líneas
    "text":        "#1a2942",   # texto principal
    "text_muted":  "#5a6b82",   # etiquetas, subtextos
    "red":         "#e53e3e",   # CRITICO
    "amber":       "#d97706",   # MODERADO
    "green":       "#059669",   # NORMAL
}

# CSS global inyectado en todas las páginas
GLOBAL_CSS = f"""
<style>
  html, body, [data-testid="stApp"] {{
    background-color: {THEME['bg']};
    font-family: 'Inter', 'Segoe UI', sans-serif;
    color: {THEME['text']};
  }}

  [data-testid="stSidebar"] {{
    background: linear-gradient(180deg, {THEME['navy']} 0%, {THEME['blue']} 100%);
  }}

  [data-testid="stSidebar"] p,
  [data-testid="stSidebar"] span,
  [data-testid="stSidebar"] label,
  [data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] {{
    color: #ffffff;
  }}

  [data-testid="stSidebar"] .stSelectbox label,
  [data-testid="stSidebar"] .stSlider label {{
    color: #ffffff !important;
    font-size: 12px !important;
    text-transform: uppercase;
    letter-spacing: .04em;
    font-weight: 600;
  }}
  [data-testid="stSidebar"] hr {{
    border-color: rgba(255,255,255,.12) !important;
  }}

  [data-testid="stSidebar"] div[data-baseweb="select"] > div {{
    background-color: rgba(255,255,255,0.15) !important;
    border-color: rgba(255,255,255,0.3) !important;
  }}
  [data-testid="stSidebar"] div[data-baseweb="select"] > div:hover {{
    border-color: rgba(255,255,255,0.5) !important;
  }}
  [data-testid="stSidebar"] [data-baseweb="select"] * {{
    color: #ffffff !important;
  }}
  [data-testid="stSidebar"] div[data-baseweb="select"] svg {{
    fill: #ffffff !important;
  }}
  div[data-baseweb="popover"] li {{
    background-color: {THEME['navy']} !important;
    color: #f5f8fc !important;
  }}
  div[data-baseweb="popover"] li:hover {{
    background-color: {THEME['blue']} !important;
  }}

  [data-testid="metric-container"] {{
    background: {THEME['surface']};
    border: 1px solid {THEME['border']};
    border-radius: 10px;
    padding: 18px 20px;
    box-shadow: 0 1px 4px rgba(10,30,60,.06);
  }}
  [data-testid="metric-container"] [data-testid="stMetricValue"] {{
    font-size: 28px !important;
    font-weight: 700 !important;
    color: {THEME['navy']} !important;
  }}
  [data-testid="metric-container"] [data-testid="stMetricLabel"] {{
    font-size: 12px !important;
    text-transform: uppercase;
    letter-spacing: .05em;
    color: {THEME['text_muted']} !important;
  }}

  .stButton > button {{
    background: {THEME['blue']};
    color: #fff;
    border: none;
    border-radius: 7px;
    padding: 9px 20px;
    font-size: 13px;
    font-weight: 500;
    transition: background .2s;
  }}
  .stButton > button:hover {{
    background: {THEME['blue_light']};
  }}

  .stTabs [data-baseweb="tab-list"] {{
    gap: 4px;
    border-bottom: 2px solid {THEME['border']};
  }}
  .stTabs [data-baseweb="tab-list"] button {{
    font-size: 13px;
    font-weight: 500;
    color: {THEME['text_muted']};
    border-radius: 6px 6px 0 0;
    padding: 8px 16px;
  }}
  .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {{
    color: {THEME['blue']};
    border-bottom: 2px solid {THEME['blue']};
  }}

  [data-testid="stDataFrame"] {{
    border: 1px solid {THEME['border']};
    border-radius: 8px;
    overflow: hidden;
  }}

  .stSelectbox div[data-baseweb="select"] {{
    border-radius: 7px;
  }}

  footer {{ visibility: hidden; }}

  ::-webkit-scrollbar {{ width: 6px; }}
  ::-webkit-scrollbar-track {{ background: {THEME['bg']}; }}
  ::-webkit-scrollbar-thumb {{ background: {THEME['border']}; border-radius: 3px; }}
</style>
"""

# ─────────────────────────────────────────────────────────────────────────────
# ALERTAS — niveles que retorna el backend (NORMAL / MODERADO / CRITICO)
# ─────────────────────────────────────────────────────────────────────────────
ALERT_LEVELS = {
    "CRITICO": {
        "color":       THEME["red"],
        "bg":          "#fef2f2",
        "label":       "Crítico",
        "description": "Acción inmediata requerida",
        "severity":    3,
    },
    "MODERADO": {
        "color":       THEME["amber"],
        "bg":          "#fffbeb",
        "label":       "Moderado",
        "description": "Monitoreo intensificado",
        "severity":    2,
    },
    "NORMAL": {
        "color":       THEME["green"],
        "bg":          "#f0fdf4",
        "label":       "Normal",
        "description": "Sin acción requerida",
        "severity":    1,
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# CACHÉ
# ─────────────────────────────────────────────────────────────────────────────
CACHE_TTL = int(os.getenv("KIM_CACHE_TTL", "300"))  # 5 min por defecto

# ─────────────────────────────────────────────────────────────────────────────
# TEXTOS UI
# ─────────────────────────────────────────────────────────────────────────────
APP_NAME        = "KIM-NEYÜN"
APP_DESCRIPTION = "Sistema predictivo de demanda asistencial"
APP_VERSION     = "1.0.0-PMV"

# Re-exportados desde shared.catalog para que el resto del frontend
# (dashboard, panel clínico) los importe siempre desde config, sin
# tener que saber de la existencia de `shared/`.
__all__ = [
    "HOSPITALES", "TRADUCCION_CAUSAS", "TRADUCCION_EDADES",
    "BACKEND_URL", "LOGIN_ENDPOINT", "ME_ENDPOINT", "HOSPITALES_ENDPOINT",
    "PREDICTION_ENDPOINT", "PROYECCION_ENDPOINT", "HEALTH_ENDPOINT", "HEALTH_DB_ENDPOINT",
    "API_TIMEOUT", "API_MAX_RETRIES", "PAGE_CONFIG", "THEME", "GLOBAL_CSS",
    "ALERT_LEVELS", "CACHE_TTL", "APP_NAME", "APP_DESCRIPTION", "APP_VERSION",
]
