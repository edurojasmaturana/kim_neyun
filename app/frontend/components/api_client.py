"""
Cliente HTTP para KIM-NEYÜN — conexión a API real en AWS Lambda
Diseñado para ser resiliente y manejar autenticación JWT
"""

import requests
import streamlit as st
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import logging
import time

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    BACKEND_URL, HOSPITALES_ENDPOINT, PREDICTION_ENDPOINT, 
    PROYECCION_ENDPOINT, API_TIMEOUT, API_MAX_RETRIES, CACHE_TTL
)

logger = logging.getLogger("kim_neyun.api_client")

# ─────────────────────────────────────────────────────────────────────────────
# ESTADO DE CONEXIÓN
# ─────────────────────────────────────────────────────────────────────────────

def check_backend_health(token: Optional[str] = None) -> Tuple[bool, str]:
    """
    Verifica si el backend está disponible.
    Retorna (disponible: bool, mensaje: str).
    """
    try:
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        
        resp = requests.get(
            f"{BACKEND_URL}/health",
            headers=headers,
            timeout=API_TIMEOUT
        )
        if resp.status_code == 200:
            return True, "Conectado"
        return False, f"HTTP {resp.status_code}"
    except requests.exceptions.ConnectionError:
        return False, "Sin conexión al servidor"
    except requests.exceptions.Timeout:
        return False, "Tiempo de espera agotado"
    except Exception as e:
        return False, f"Error inesperado: {str(e)}"


# ─────────────────────────────────────────────────────────────────────────────
# CLIENTE BASE
# ─────────────────────────────────────────────────────────────────────────────

def _get(
    endpoint: str,
    token: str,
    params: Optional[Dict] = None,
    retries: int = API_MAX_RETRIES,
) -> Tuple[bool, Optional[Dict], str]:
    """
    GET con reintentos automáticos.
    Retorna (éxito, datos, mensaje_error).
    """
    headers = {"Authorization": f"Bearer {token}"}
    
    for attempt in range(retries):
        try:
            resp = requests.get(
                endpoint,
                params=params,
                headers=headers,
                timeout=API_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            return True, data, ""

        except requests.exceptions.HTTPError as e:
            msg = f"Error HTTP {e.response.status_code}"
            if e.response.status_code == 401:
                return False, None, "Token expirado o inválido"
            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))
            else:
                return False, None, msg

        except requests.exceptions.ConnectionError:
            msg = "Backend no disponible"
            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))
            else:
                return False, None, msg

        except requests.exceptions.Timeout:
            msg = "Tiempo de espera agotado"
            if attempt < retries - 1:
                time.sleep(0.5)
            else:
                return False, None, msg

        except ValueError:
            return False, None, "Respuesta inválida del servidor"

        except Exception as e:
            logger.exception("Error inesperado en _get")
            return False, None, str(e)

    return False, None, "No se pudo conectar después de varios intentos"


def _post(
    endpoint: str,
    token: str,
    json_data: Dict,
    retries: int = API_MAX_RETRIES,
) -> Tuple[bool, Optional[Dict], str]:
    """
    POST con reintentos automáticos.
    Retorna (éxito, datos, mensaje_error).
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    for attempt in range(retries):
        try:
            resp = requests.post(
                endpoint,
                json=json_data,
                headers=headers,
                timeout=API_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            return True, data, ""

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                return False, None, "Token expirado o inválido"
            if e.response.status_code == 404:
                return False, None, "No hay predicción disponible para esos parámetros"
            if e.response.status_code == 422:
                return False, None, "Datos inválidos (revisar formato)"
            
            msg = f"Error HTTP {e.response.status_code}"
            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))
            else:
                return False, None, msg

        except requests.exceptions.ConnectionError:
            msg = "Backend no disponible"
            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))
            else:
                return False, None, msg

        except requests.exceptions.Timeout:
            msg = "Tiempo de espera agotado"
            if attempt < retries - 1:
                time.sleep(0.5)
            else:
                return False, None, msg

        except ValueError:
            return False, None, "Respuesta inválida del servidor"

        except Exception as e:
            logger.exception("Error inesperado en _post")
            return False, None, str(e)

    return False, None, "No se pudo conectar después de varios intentos"


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS PÚBLICOS
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=CACHE_TTL)
def fetch_hospitales(token: str) -> Dict:
    """
    Obtiene el catálogo de centros disponibles.
    
    Returns:
        {
          "success": bool,
          "data": { "hospitales": [...] },
          "error": str | None
        }
    """
    ok, data, error = _get(HOSPITALES_ENDPOINT, token)
    
    if ok and data:
        hospitales = data.get("hospitales", [])
        return {
            "success": True,
            "data": {"hospitales": hospitales},
            "error": None,
        }
    
    return {
        "success": False,
        "data": {"hospitales": []},
        "error": error or "Error desconocido",
    }


@st.cache_data(ttl=CACHE_TTL)
def fetch_prediction(
    token: str,
    establecimiento: str,
    fecha_referencia: str,
) -> Dict:
    """
    Obtiene predicción táctica para una semana específica.
    
    Args:
        token: JWT bearer token
        establecimiento: Nombre exacto del hospital (ej: "Hospital Dr. Hernán Henríquez Aravena (Temuco)")
        fecha_referencia: Fecha en formato YYYY-MM-DD (cualquier día de la semana a consultar)
    
    Returns:
        {
          "success": bool,
          "data": { prediction_response },
          "error": str | None
        }
    """
    payload = {
        "EstablecimientoGlosa": establecimiento,
        "fecha_referencia": fecha_referencia,
    }
    
    ok, data, error = _post(PREDICTION_ENDPOINT, token, payload)
    
    if ok and data:
        return {
            "success": True,
            "data": data,
            "error": None,
        }
    
    return {
        "success": False,
        "data": {},
        "error": error or "Error desconocido",
    }


@st.cache_data(ttl=CACHE_TTL)
def fetch_proyeccion_anual(
    token: str,
    establecimiento: str,
    anio_proyeccion: int,
) -> Dict:
    """
    Obtiene proyección estratégica (52 semanas).
    
    Args:
        token: JWT bearer token
        establecimiento: Nombre exacto del hospital
        anio_proyeccion: Año (ej: 2026)
    
    Returns:
        {
          "success": bool,
          "data": { annual_projection },
          "error": str | None
        }
    """
    payload = {
        "EstablecimientoGlosa": establecimiento,
        "anio_proyeccion": anio_proyeccion,
    }
    
    ok, data, error = _post(PROYECCION_ENDPOINT, token, payload)
    
    if ok and data:
        return {
            "success": True,
            "data": data,
            "error": None,
        }
    
    return {
        "success": False,
        "data": {},
        "error": error or "Error desconocido",
    }


def invalidate_cache():
    """Limpia la caché de Streamlit para forzar recarga desde el backend."""
    fetch_hospitales.clear()
    fetch_prediction.clear()
    fetch_proyeccion_anual.clear()


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS DE UI
# ─────────────────────────────────────────────────────────────────────────────

def render_connection_badge(token: Optional[str] = None):
    """
    Muestra en la sidebar un badge de estado de conexión.
    Verde = conectado, rojo = problema.
    """
    available, msg = check_backend_health(token)
    if available:
        st.sidebar.markdown(
            f"""
            <div style="
                background:#10b98122;
                border:1px solid #10b981;
                border-radius:6px;
                padding:8px 12px;
                font-size:12px;
                color:#10b981;
                margin-bottom:12px;
            ">
                <span style="font-size:10px;">●</span> Backend conectado
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.sidebar.markdown(
            f"""
            <div style="
                background:#f59e0b18;
                border:1px solid #f59e0b;
                border-radius:6px;
                padding:8px 12px;
                font-size:12px;
                color:#b45309;
                margin-bottom:12px;
            ">
                <span style="font-size:10px;">●</span> Backend no disponible
                <br><span style="opacity:.7;font-size:11px;">{msg}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    return available
