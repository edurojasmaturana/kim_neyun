"""
Componentes de tarjetas KPI para KIM-NEYUN
"""

import streamlit as st
from config import THEME, ALERT_LEVELS


def kpi_card(label, value, subtitle="", color=None, icon=None):
    st.metric(label=label, value=value, help=subtitle)


def alert_summary_card(rojo, amarillo, verde, compact=False):
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Critico", rojo)
    with c2:
        st.metric("Moderado", amarillo)
    with c3:
        st.metric("Normal", verde)


def alert_row(alert):
    level = alert.get("level", "VERDE")
    cfg = ALERT_LEVELS.get(level, ALERT_LEVELS["VERDE"])
    confidence_pct = int(alert.get("confidence", 0) * 100)
    hospital = alert.get("hospital") or "Todos los establecimientos"

    color_map = {"ROJO": "🔴", "AMARILLO": "🟡", "VERDE": "🟢"}
    icon = color_map.get(level, "🟢")

    with st.container():
        col1, col2 = st.columns([4, 1])
        with col1:
            st.markdown(f"{icon} **{alert.get('pathology', '')}** — {alert.get('message', '')}")
            st.caption(f"{alert.get('region', '')} · {hospital}")
        with col2:
            st.metric("Confianza", f"{confidence_pct}%")
        st.divider()


def page_header(title, subtitle=""):
    st.subheader(title)
    if subtitle:
        st.caption(subtitle)


def demo_banner():
    st.warning("**Modo demostración** — El backend no esta disponible. Los datos mostrados son simulados para validacion del PMV.")
