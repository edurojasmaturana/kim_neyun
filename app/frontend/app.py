"""Dashboard KIM-NEYÜN (Streamlit).

Adaptado del PoC (`poc/app (poc).py`): única diferencia funcional es que la URL
del backend se toma de la variable de entorno `API_BASE_URL` (antes era
http://localhost:8000 fijo) y el catálogo/traducciones se importan de
`shared.catalog` para no duplicar.
"""

import datetime
import os
import random

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

from shared.catalog import HOSPITALES, TRADUCCION_CAUSAS, TRADUCCION_EDADES

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000").rstrip("/")


def auth_headers() -> dict:
    """Cabecera Bearer con el JWT de la sesión (vacía si no hay sesión)."""
    token = st.session_state.get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def do_login(email: str, password: str) -> str | None:
    """Pide un token al backend. Devuelve un mensaje de error o None si OK."""
    try:
        # OAuth2 password flow: el backend espera form-data (username = email).
        resp = requests.post(
            f"{API_BASE_URL}/auth/login",
            data={"username": email.strip().lower(), "password": password},
            timeout=30,
        )
        if resp.status_code == 200:
            st.session_state["token"] = resp.json()["access_token"]
            st.session_state["email"] = email.strip().lower()
            return None
        return resp.json().get("detail", "Credenciales incorrectas.")
    except Exception as e:  # noqa: BLE001
        return f"No se pudo contactar el backend: {e}"


def require_login() -> None:
    """Muestra el formulario de login y detiene la app si no hay sesión."""
    if st.session_state.get("token"):
        return
    st.title("🔐 Acceso a KIM-NEYÜN")
    st.caption("Ingrese sus credenciales para acceder al sistema.")
    with st.form("login"):
        email = st.text_input("Email")
        password = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Iniciar sesión", type="primary"):
            err = do_login(email, password)
            if err:
                st.error(err)
            else:
                st.rerun()
    st.stop()


def set_seed(seed=42):
    random.seed(seed)
    np.random.seed(seed)


set_seed(42)

st.set_page_config(page_title="KIM-NEYÜN - Gestión Respiratoria", page_icon="🫁", layout="wide")

# --- ESTILOS Y CRÉDITOS ---
st.sidebar.title("KIM-NEYÜN")
st.sidebar.markdown("*Saber de la Respiración*")
st.sidebar.divider()
st.sidebar.markdown(
    """
**Desarrollado por:**
* **TM Eduardo Rojas Maturana**
* **Dr. TM Neftalí Guzmán Oyarzo**

Facultad de Ciencias de la Salud, UCT.
*Laboratorio de Investigación en Salud de Precisión.*
---
"""
)
st.sidebar.info(
    "**KIM-NEYÜN** utiliza un ruteo inteligente HZF (Chronos + XGBoost) para la "
    "predicción clínica y planificación de recursos."
)
st.sidebar.caption(f"Backend: {API_BASE_URL}")

# Puerta de autenticación: sin sesión, solo se muestra el login.
require_login()

st.sidebar.divider()
st.sidebar.caption(f"Sesión: {st.session_state.get('email', '')}")
if st.sidebar.button("Cerrar sesión"):
    st.session_state.pop("token", None)
    st.session_state.pop("email", None)
    st.rerun()

tab1, tab2, tab3, tab4 = st.tabs(
    ["🚀 Urgencias (Micro)", "📅 Planificación Anual (Macro)", "📖 Manual de Usuario", "📊 Metodología"]
)

# --- TÁCTICO: 1 SEMANA ---
with tab1:
    st.title("Sistema de Estimación de Urgencias Respiratorias")
    st.markdown("### 🏥 Panel Operativo de Invierno (Táctico)")
    st.warning("📅 **Pronóstico Semanal:** Evalúa inercia y corrige utilizando el clima actual.")

    col_input, col_date = st.columns(2)
    with col_input:
        hosp_sel = st.selectbox("Seleccione Centro de Salud:", HOSPITALES, key="hosp1")

    with col_date:
        fecha_input = st.date_input("Seleccione semana (Cualquier día):", datetime.date.today())
        # Retrocede siempre al DOMINGO de esa semana (inicio de semana epidemiológica).
        dias_a_restar = (fecha_input.weekday() + 1) % 7
        domingo_semana = fecha_input - datetime.timedelta(days=dias_a_restar)
        if fecha_input != domingo_semana:
            st.info(
                f"Ajustado al inicio de la Semana Epidemiológica: "
                f"**Domingo {domingo_semana.strftime('%d/%m/%Y')}**."
            )

    if st.button("🚀 Ejecutar Análisis Táctico", type="primary"):
        with st.spinner("Consultando predicciones precomputadas (Chronos + XGBoost)..."):
            try:
                payload = {
                    "EstablecimientoGlosa": hosp_sel,
                    "fecha_referencia": domingo_semana.strftime("%Y-%m-%d"),
                }
                response = requests.post(
                    f"{API_BASE_URL}/predecir", json=payload, headers=auth_headers(), timeout=30
                )
                if response.status_code == 401:
                    st.warning("Sesión expirada. Vuelva a iniciar sesión.")
                    st.session_state.pop("token", None)
                    st.rerun()
                data = response.json()

                if response.status_code != 200:
                    st.error(f"Error: {data.get('detail', 'Desconocido')}")
                else:
                    st.success(f"📅 **Semana Epidemiológica {data['semana_epi']} - {data['año']}**")
                    m1, m2, m3 = st.columns(3)
                    total_est = data["estimaciones"]["Total"]
                    m1.metric("Consultas Semanales", total_est)

                    # Prefiere el nivel del backend; si no viene, usa el umbral del PoC.
                    alerta = data.get("nivel_alerta") or ("PREEMERGENCIA" if total_est > 150 else "NORMAL")
                    if alerta == "PREEMERGENCIA":
                        st.error("🚨 **ALERTA INVIERNO:** Volumen excede margen.")
                    m2.metric("Nivel de Alerta", alerta)
                    m3.metric("Temp. Estructural", f"{round(data.get('temperatura_referencia') or 0, 1)} °C")

                    col_plot1, col_plot2 = st.columns(2)
                    with col_plot1:
                        df_c = pd.DataFrame(
                            list(data["estimaciones"]["Causas"].items()), columns=["Causa", "Casos"]
                        )
                        df_c["Causa"] = df_c["Causa"].map(TRADUCCION_CAUSAS).fillna(df_c["Causa"])
                        df_c = df_c.sort_values(by="Casos", ascending=True)
                        fig_causas = px.bar(
                            df_c, x="Casos", y="Causa", orientation="h", color="Casos",
                            color_continuous_scale="Blues", text_auto=True,
                        )
                        fig_causas.update_layout(showlegend=False, yaxis_title="", title="Desglose Etiológico")
                        st.plotly_chart(fig_causas, use_container_width=True)

                    with col_plot2:
                        df_e = pd.DataFrame(
                            list(data["estimaciones"]["Edades"].items()), columns=["Grupo", "Casos"]
                        )
                        df_e["Grupo"] = df_e["Grupo"].map(TRADUCCION_EDADES).fillna(df_e["Grupo"])
                        fig_edades = px.pie(
                            df_e, values="Casos", names="Grupo", hole=0.4,
                            color_discrete_sequence=px.colors.sequential.Teal_r,
                            title="Vulnerabilidad Etaria",
                        )
                        st.plotly_chart(fig_edades, use_container_width=True)
            except Exception as e:
                st.error(f"Error de conexión: {e}")

# --- ESTRATÉGICO: 52 SEMANAS ---
with tab2:
    st.title("Proyección Estratégica a 52 Semanas")
    st.markdown("### 📈 Panel de Planificación y Control (Macro)")
    st.info(
        "Esta herramienta evalúa la **Curva Base de IA** para licitaciones y compras. "
        "Si selecciona un año pasado (ej. 2024), el modelo hará un control retrospectivo "
        "comparando su proyección *ciega* contra los casos que realmente ocurrieron."
    )

    col_hosp_m, col_anio_m = st.columns(2)
    with col_hosp_m:
        hosp_macro = st.selectbox("Seleccione Centro de Salud:", HOSPITALES, key="hosp2")
    with col_anio_m:
        anio_macro = st.selectbox("Año de Proyección:", [2024, 2025, 2026])

    if st.button("📊 Generar Curva Anual", type="primary"):
        with st.spinner("Consultando proyección anual precomputada..."):
            try:
                payload = {"EstablecimientoGlosa": hosp_macro, "anio_proyeccion": anio_macro}
                response = requests.post(
                    f"{API_BASE_URL}/proyeccion_anual", json=payload, headers=auth_headers(), timeout=30
                )
                if response.status_code == 401:
                    st.warning("Sesión expirada. Vuelva a iniciar sesión.")
                    st.session_state.pop("token", None)
                    st.rerun()
                data = response.json()

                if response.status_code != 200:
                    st.error(f"Error: {data.get('detail', 'Desconocido')}")
                else:
                    semanas = data["semanas"]
                    curva_ia = data["curva_ia"]
                    curva_real = data["curva_real"]
                    volumen_esperado = sum(curva_ia)

                    m1_macro, m2_macro = st.columns(2)
                    m1_macro.metric("Estimación Total Anual (IA)", f"{volumen_esperado:,}".replace(",", "."))

                    fig_macro = go.Figure()
                    fig_macro.add_trace(
                        go.Scatter(x=semanas, y=curva_ia, mode="lines+markers",
                                   name="Proyección IA Base", line=dict(color="blue", width=3))
                    )
                    datos_reales_validos = [x for x in curva_real if x is not None]
                    if datos_reales_validos:
                        fig_macro.add_trace(
                            go.Scatter(x=semanas, y=curva_real, mode="lines",
                                       name="Realidad Hospitalaria (DEIS)",
                                       line=dict(color="red", dash="dot", width=2))
                        )
                        vol_real = sum(datos_reales_validos)
                        m2_macro.metric(f"Total Histórico Real ({anio_macro})", f"{vol_real:,}".replace(",", "."))

                    fig_macro.update_layout(
                        title=f"Curva Epidemiológica Anual - {anio_macro}",
                        xaxis_title="Semana Epidemiológica",
                        yaxis_title="Volumen de Consultas Respiratorias",
                        hovermode="x unified",
                    )
                    st.plotly_chart(fig_macro, use_container_width=True)
            except Exception as e:
                st.error(f"Error de conexión con el motor macro: {e}")

with tab3:
    st.header("📖 Manual de Usuario y Auditoría")
    st.write("Explicación del uso del sistema...")

with tab4:
    st.header("📊 Metodología: Arquitectura Fundacional Híbrida")
    st.write("KIM-NEYÜN utiliza Inteligencia Artificial HZF (Chronos + XGBoost)...")
