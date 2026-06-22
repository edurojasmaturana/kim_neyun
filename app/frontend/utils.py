"""
Funciones auxiliares para KIM-NEYÜN
"""

import streamlit as st
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import io


# ─────────────────────────────────────────────────────────────────────────────
# FORMATO
# ─────────────────────────────────────────────────────────────────────────────

def format_number(num: float, decimals: int = 0) -> str:
    """Formatea con separadores de miles estilo chileno (puntos)."""
    if decimals == 0:
        return f"{int(num):,}".replace(",", ".")
    return f"{num:,.{decimals}f}".replace(",", "X").replace(".", ".").replace("X", ",")


def format_percentage(value: float, decimals: int = 1) -> str:
    """Convierte 0.95 → '95.0%'."""
    return f"{value * 100:.{decimals}f}%"


def get_time_ago(timestamp: str) -> str:
    """Convierte timestamp ISO a 'hace X minutos/horas'."""
    try:
        dt   = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        now  = datetime.now(dt.tzinfo)
        diff = now - dt

        if diff.total_seconds() < 60:
            return "hace unos segundos"
        elif diff.total_seconds() < 3600:
            m = int(diff.total_seconds() // 60)
            return f"hace {m} minuto{'s' if m != 1 else ''}"
        elif diff.total_seconds() < 86400:
            h = int(diff.total_seconds() // 3600)
            return f"hace {h} hora{'s' if h != 1 else ''}"
        else:
            return f"hace {diff.days} día{'s' if diff.days != 1 else ''}"
    except Exception:
        return timestamp


# ─────────────────────────────────────────────────────────────────────────────
# SESIÓN
# ─────────────────────────────────────────────────────────────────────────────

def initialize_session_state():
    """Inicializa variables de sesión con valores por defecto."""
    defaults = {
        "last_refresh":        datetime.now(),
        "selected_pathology":  "Influenza",
        "selected_region":     "Metropolitana",
        "selected_hospital":   None,
        "api_error":           None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ─────────────────────────────────────────────────────────────────────────────
# ALERTAS
# ─────────────────────────────────────────────────────────────────────────────

def get_alert_count_by_level(alerts: List[Dict]) -> Dict[str, int]:
    """Cuenta alertas agrupadas por nivel."""
    counts = {"ROJO": 0, "AMARILLO": 0, "VERDE": 0}
    for alert in alerts:
        level = alert.get("level", "VERDE")
        if level in counts:
            counts[level] += 1
    return counts


def get_highest_alert_level(alerts: List[Dict]) -> str:
    """Retorna el nivel de alerta más crítico presente en la lista."""
    severity = {"ROJO": 3, "AMARILLO": 2, "VERDE": 1}
    if not alerts:
        return "VERDE"
    max_sev = max(severity.get(a.get("level", "VERDE"), 0) for a in alerts)
    for level, sev in severity.items():
        if sev == max_sev:
            return level
    return "VERDE"


# ─────────────────────────────────────────────────────────────────────────────
# EXPORTACIÓN
# ─────────────────────────────────────────────────────────────────────────────

def export_to_csv(df: pd.DataFrame) -> bytes:
    """Convierte DataFrame a bytes CSV (UTF-8 con BOM para compatibilidad Excel)."""
    return df.to_csv(index=False).encode("utf-8-sig")


def export_to_excel(df: pd.DataFrame, sheet_name: str = "Datos") -> bytes:
    """Convierte DataFrame a bytes Excel."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
        # Ajustar ancho de columnas
        ws = writer.sheets[sheet_name]
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 40)
    return output.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# VALIDACIÓN
# ─────────────────────────────────────────────────────────────────────────────

def validate_api_response(response: Dict) -> Tuple[bool, Optional[str]]:
    """
    Valida estructura básica de respuesta de API.
    Retorna (válida, mensaje_error).
    """
    if not response.get("success", False):
        return False, response.get("error", "Error desconocido en la API")
    if not response.get("data"):
        return False, "El servidor retornó una respuesta vacía"
    return True, None


def predictions_to_dataframe(predictions: List[Dict]) -> pd.DataFrame:
    """
    Convierte lista de predicciones a DataFrame normalizado.
    """
    if not predictions:
        return pd.DataFrame(columns=["date", "predicted_cases", "confidence"])
    df = pd.DataFrame(predictions)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    if "confidence" not in df.columns:
        df["confidence"] = 0.0
    return df


def alerts_to_dataframe(alerts: List[Dict]) -> pd.DataFrame:
    """
    Convierte lista de alertas a DataFrame normalizado.
    """
    if not alerts:
        return pd.DataFrame()
    df = pd.DataFrame(alerts)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df
