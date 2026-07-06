"""
KIM-NEYUN - Estimacion de Demanda de Urgencias
Tab 1: Urgencias (semana especifica)
Tab 2: Manual de usuario
"""
import streamlit as st
import plotly.graph_objects as go
import sys, os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if "token" not in st.session_state or not st.session_state.token:
    st.switch_page("pages/login.py")

from config import (
    PAGE_CONFIG, GLOBAL_CSS, APP_NAME, APP_VERSION,
    TRADUCCION_CAUSAS, TRADUCCION_EDADES,
)
from components.api_client import fetch_prediction, fetch_hospitales, render_connection_badge
from utils import (
    initialize_session_state, get_semana_epi, traducir_causa, traducir_edad,
    handle_api_error_and_maybe_logout, render_logout_button, fecha_maxima_consultable,
)
import base64

# Logo UCTemuco
try:
    logo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "logo.png")
    with open(logo_path, "rb") as f:
        LOGO_UCT = "data:image/png;base64," + base64.b64encode(f.read()).decode()
except Exception:
    LOGO_UCT = None
    
st.set_page_config(**PAGE_CONFIG)
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
initialize_session_state()


with st.sidebar:
    st.markdown(
        f'<div style="padding:16px 0 20px 0;border-bottom:1px solid rgba(255,255,255,.12);margin-bottom:20px;">'
        f'<div style="font-size:20px;font-weight:700;color:#fff;">{APP_NAME}</div>'
        f'<div style="font-size:11px;color:rgba(255,255,255,.5);margin-top:3px;">Estimacion de Demanda de Urgencias</div>'
        f'<div style="font-size:10px;color:rgba(255,255,255,.3);margin-top:6px;">v{APP_VERSION}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    
    st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)
    render_logout_button()

logo_html = (
    f'<img src="{LOGO_UCT}" style="position:absolute;top:16px;right:20px;'
    f'height:100px;opacity:0.95;filter:brightness(0) invert(1);" alt="UCTemuco"/>'
    if LOGO_UCT else ""
)

st.markdown(
    f'<div style="background:linear-gradient(135deg,#0369a1 0%,#0ea5e9 100%);'
    f'border-radius:12px;padding:20px 24px;margin-bottom:24px;color:#fff;position:relative;">'
    f'<div style="font-size:10px;text-transform:uppercase;letter-spacing:.1em;opacity:.65;margin-bottom:5px;">'
    f'Sistema predictivo de demanda asistencial</div>'
    f'<div style="font-size:22px;font-weight:700;">Estimación de Demanda de Urgencias</div>'
    f'<div style="font-size:12px;opacity:.7;margin-top:3px;">Análisis semanal y guía de interpretación clínica</div>'
    f'{logo_html}</div>',
    unsafe_allow_html=True,
)

tab1, tab2 = st.tabs(["🚨 Urgencias", "📖 Manual de usuario"])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — URGENCIAS TÁCTICAS
# ─────────────────────────────────────────────────────────────────────────────
with tab1:
    token = st.session_state.get("token")
    hospitales_result = fetch_hospitales(token)

    if not hospitales_result["success"]:
        if handle_api_error_and_maybe_logout(hospitales_result["error"]):
            st.stop()
        st.error(f"No se pudieron cargar los centros asistenciales: {hospitales_result['error']}")
        st.stop()

    hospitales_list = hospitales_result["data"].get("hospitales", [])

    if not hospitales_list:
        st.error("No se pudieron cargar los centros asistenciales.")
        st.stop()

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(
            '<div style="font-size:11px;color:#5a6b82;text-transform:uppercase;'
            'letter-spacing:.05em;margin-bottom:6px;font-weight:600;">Centro asistencial</div>',
            unsafe_allow_html=True,
        )
        hosp_sel = st.selectbox(
            "Centro asistencial",
            hospitales_list,
            key="panel_hosp",
            label_visibility="collapsed",
        )
    with col_b:
        st.markdown(
            '<div style="font-size:11px;color:#5a6b82;text-transform:uppercase;'
            'letter-spacing:.05em;margin-bottom:6px;font-weight:600;">Fecha de referencia</div>',
            unsafe_allow_html=True,
        )
        fecha_sel = st.date_input(
            "Fecha de referencia",
            value=date.today(),
            min_value=date(2024, 1, 1),
            max_value=fecha_maxima_consultable(),
            key="panel_fecha",
            label_visibility="collapsed",
            format="DD/MM/YYYY",
        )

    iso_year, iso_week, domingo_se = get_semana_epi(fecha_sel)

    st.markdown(
        f'<div style="background:#e0f2fe;border-radius:6px;padding:8px 14px;'
        f'margin-bottom:16px;font-size:12px;color:#0369a1;">'
        f'Ajustado a Semana Epidemiológica <strong>SE {iso_week} — {iso_year}</strong> '
        f'(domingo {domingo_se.strftime("%d/%m/%Y")})'
        f'</div>',
        unsafe_allow_html=True,
    )

    ejecutar = st.button("▶ Ejecutar análisis", type="primary", use_container_width=False)

    if ejecutar:
        with st.spinner("Consultando predicciones precomputadas (Chronos + XGBoost)..."):
            fecha_referencia = domingo_se.strftime("%Y-%m-%d")
            pred_result = fetch_prediction(
                token=token,
                establecimiento=hosp_sel,
                fecha_referencia=fecha_referencia,
            )

        if not pred_result["success"]:
            error_msg = pred_result["error"]
            if handle_api_error_and_maybe_logout(error_msg):
                st.stop()
            if "404" in str(error_msg) or "No hay predicción" in str(error_msg):
                st.warning(
                    f"No hay predicción precomputada para la semana del "
                    f"{domingo_se.strftime('%d/%m/%Y')} en {hosp_sel}. "
                    f"El sistema cubre un rango limitado de semanas; "
                    f"prueba con la semana actual."
                )
            else:
                st.error(f"Error: {error_msg}")
        else:
            data = pred_result["data"]
            semana_epi   = data.get("semana_epi", iso_week)
            anio         = data.get("año", iso_year)
            estimaciones = data.get("estimaciones", {})
            causas       = estimaciones.get("Causas", {})
            edades       = estimaciones.get("Edades", {})
            total_casos  = estimaciones.get("Total", 0)
            temperatura  = data.get("temperatura_referencia")
            nivel_alerta = data.get("nivel_alerta") or "NORMAL"
            temp_str     = f"{round(temperatura, 1)} °C" if temperatura is not None else "N/D"
            color_alerta = (
                "#e53e3e" if nivel_alerta.upper() == "CRITICO"
                else "#d97706" if nivel_alerta.upper() == "MODERADO"
                else "#059669"
            )

            st.success(f"📅 Semana Epidemiológica {semana_epi} — {anio}")

            m1, m2, m3 = st.columns(3)
            with m1:
                st.markdown(
                    f'<div style="background:#fff;border:1px solid #dde3ed;border-top:3px solid #0ea5e9;'
                    f'border-radius:8px;padding:12px 14px;">'
                    f'<div style="font-size:9px;text-transform:uppercase;letter-spacing:.06em;color:#5a6b82;margin-bottom:4px;">Consultas semanales estimadas</div>'
                    f'<div style="font-size:26px;font-weight:600;color:#0369a1;">{int(total_casos)}</div>'
                    f'<div style="font-size:11px;color:#5a6b82;margin-top:2px;">SE {semana_epi} · {hosp_sel}</div></div>',
                    unsafe_allow_html=True,
                )
            with m2:
                st.markdown(
                    f'<div style="background:#fff;border:1px solid #dde3ed;border-top:3px solid {color_alerta};'
                    f'border-radius:8px;padding:12px 14px;">'
                    f'<div style="font-size:9px;text-transform:uppercase;letter-spacing:.06em;color:#5a6b82;margin-bottom:4px;">Nivel de alerta</div>'
                    f'<div style="font-size:20px;font-weight:600;color:{color_alerta};">{nivel_alerta.capitalize()}</div>'
                    f'<div style="font-size:11px;color:#5a6b82;margin-top:2px;">Volumen vs. umbral histórico</div></div>',
                    unsafe_allow_html=True,
                )
            with m3:
                st.markdown(
                    f'<div style="background:#fff;border:1px solid #dde3ed;border-top:3px solid #d97706;'
                    f'border-radius:8px;padding:12px 14px;">'
                    f'<div style="font-size:9px;text-transform:uppercase;letter-spacing:.06em;color:#5a6b82;margin-bottom:4px;">Temperatura estructural</div>'
                    f'<div style="font-size:26px;font-weight:600;color:#0369a1;">{temp_str}</div>'
                    f'<div style="font-size:11px;color:#5a6b82;margin-top:2px;">promedio semana ref.</div></div>',
                    unsafe_allow_html=True,
                )

            st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)

            col_p1, col_p2 = st.columns(2)
            with col_p1:
                if causas:
                    causas_ord = sorted(causas.items(), key=lambda x: x[1], reverse=True)
                    nombres = [traducir_causa(k, TRADUCCION_CAUSAS) for k, _ in causas_ord]
                    valores = [v for _, v in causas_ord]
                    fig = go.Figure(go.Bar(
                        x=valores, y=nombres, orientation="h",
                        marker=dict(color="#0ea5e9", line=dict(color="rgba(0,0,0,0)")),
                        text=[str(int(v)) for v in valores],
                        textposition="outside",
                        textfont=dict(size=11, color="#0369a1"),
                    ))
                    fig.update_layout(
                        title=dict(text="Desglose etiológico", font=dict(size=13, color="#0369a1"), x=0),
                        font=dict(family="Inter, sans-serif", color="#5a6b82"),
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        margin=dict(l=12, r=50, t=44, b=12),
                        xaxis=dict(gridcolor="#e0f2fe"),
                        yaxis=dict(autorange="reversed"),
                        height=300, showlegend=False,
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("Sin desglose de causas disponible.")

            with col_p2:
                if edades:
                    edades_ord = sorted(edades.items(), key=lambda x: x[1], reverse=True)
                    nombres_e = [traducir_edad(k, TRADUCCION_EDADES) for k, _ in edades_ord]
                    valores_e = [v for _, v in edades_ord]
                    fig2 = go.Figure(go.Pie(
                        labels=nombres_e, values=valores_e, hole=0.4,
                        marker=dict(colors=["#0369a1", "#0ea5e9", "#38bdf8", "#7dd3fc", "#bae6fd"]),
                    ))
                    fig2.update_layout(
                        title=dict(text="Vulnerabilidad etaria", font=dict(size=13, color="#0369a1"), x=0),
                        font=dict(family="Inter, sans-serif", color="#5a6b82"),
                        paper_bgcolor="rgba(0,0,0,0)",
                        margin=dict(l=12, r=12, t=44, b=12),
                        height=300,
                    )
                    st.plotly_chart(fig2, use_container_width=True)
                else:
                    st.info("Sin desglose etario disponible.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — MANUAL DE USUARIO
# ─────────────────────────────────────────────────────────────────────────────
with tab2:
    st.markdown('<div style="background:#fff;border:1px solid #dde3ed;border-radius:10px;padding:24px;margin-bottom:16px;"><div style="font-size:16px;font-weight:600;color:#0369a1;margin-bottom:12px;">¿Qué es KIM-NEYÜN?</div><p style="color:#374151;font-size:14px;line-height:1.7;margin:0;">KIM-NEYÜN es una plataforma de soporte a la decisión clínica que estima el volumen de consultas respiratorias esperadas para la semana epidemiológica entrante, integrando datos históricos del DEIS y variables ambientales (temperatura, calidad del aire) con rezago biológico.</p></div>', unsafe_allow_html=True)

    st.markdown('<div style="background:#fff;border:1px solid #dde3ed;border-radius:10px;padding:24px;margin-bottom:16px;"><div style="font-size:16px;font-weight:600;color:#0369a1;margin-bottom:10px;">Cómo funciona KIM-NEYÜN</div><p style="color:#374151;font-size:14px;line-height:1.7;margin:0 0 14px 0;">KIM-NEYÜN integra un sistema híbrido de pronóstico (arquitectura HZF) para proyectar la demanda asistencial respiratoria, combinando series de tiempo históricas con variables ambientales de rezago biológico.</p><div style="display:flex;gap:8px;flex-wrap:wrap;"><span style="background:#eff6ff;color:#0369a1;border:1px solid #bfdbfe;border-radius:5px;padding:4px 12px;font-size:12px;font-weight:600;">Chronos-T5</span><span style="background:#eff6ff;color:#0369a1;border:1px solid #bfdbfe;border-radius:5px;padding:4px 12px;font-size:12px;font-weight:600;">XGBoost / Ridge</span><span style="background:#eff6ff;color:#0369a1;border:1px solid #bfdbfe;border-radius:5px;padding:4px 12px;font-size:12px;font-weight:600;">PCA</span></div></div>', unsafe_allow_html=True)

    st.markdown('<div style="background:#fff;border:1px solid #dde3ed;border-radius:10px;padding:24px;margin-bottom:16px;"><div style="font-size:16px;font-weight:600;color:#0369a1;margin-bottom:16px;">Sistema de alertas semafóricas</div><table style="width:100%;border-collapse:collapse;font-size:13px;"><thead><tr style="background:#f0f4f8;"><th style="padding:10px 14px;text-align:left;color:#5a6b82;font-weight:600;text-transform:uppercase;font-size:11px;letter-spacing:.05em;border-bottom:2px solid #dde3ed;">Nivel</th><th style="padding:10px 14px;text-align:left;color:#5a6b82;font-weight:600;text-transform:uppercase;font-size:11px;letter-spacing:.05em;border-bottom:2px solid #dde3ed;">Condición</th><th style="padding:10px 14px;text-align:left;color:#5a6b82;font-weight:600;text-transform:uppercase;font-size:11px;letter-spacing:.05em;border-bottom:2px solid #dde3ed;">Acción recomendada</th></tr></thead><tbody><tr style="border-bottom:1px solid #f0f4f8;"><td style="padding:12px 14px;"><span style="background:#fef2f2;color:#e53e3e;border:1px solid #e53e3e;border-radius:5px;padding:3px 10px;font-weight:600;font-size:12px;">Crítico</span></td><td style="padding:12px 14px;color:#374151;">Volumen estimado supera el percentil crítico (P90) del histórico del establecimiento</td><td style="padding:12px 14px;color:#374151;">Activar protocolo de contingencia, reforzar dotación, revisar disponibilidad de camas</td></tr><tr style="border-bottom:1px solid #f0f4f8;"><td style="padding:12px 14px;"><span style="background:#fffbeb;color:#d97706;border:1px solid #d97706;border-radius:5px;padding:3px 10px;font-weight:600;font-size:12px;">Moderado</span></td><td style="padding:12px 14px;color:#374151;">Volumen entre el percentil 75 y 90 del histórico, zona de alerta</td><td style="padding:12px 14px;color:#374151;">Monitoreo intensificado, pre-asignación preventiva de turnos adicionales</td></tr><tr><td style="padding:12px 14px;"><span style="background:#f0fdf4;color:#059669;border:1px solid #059669;border-radius:5px;padding:3px 10px;font-weight:600;font-size:12px;">Normal</span></td><td style="padding:12px 14px;color:#374151;">Volumen proyectado dentro del rango histórico esperado</td><td style="padding:12px 14px;color:#374151;">Operación estándar, sin ajuste de recursos</td></tr></tbody></table></div>', unsafe_allow_html=True)

    st.markdown('<div style="background:#fff;border:1px solid #dde3ed;border-radius:10px;padding:24px;margin-bottom:16px;"><div style="font-size:16px;font-weight:600;color:#0369a1;margin-bottom:12px;">Semana epidemiológica</div><p style="color:#374151;font-size:14px;line-height:1.7;margin:0;">El sistema trabaja con semanas epidemiológicas (SE) según estándar CDC/MINSAL. Al seleccionar cualquier fecha del calendario, KIM-NEYÜN ajusta automáticamente al domingo de inicio de esa semana estadística. La estimación entregada corresponde al volumen total de consultas respiratorias proyectadas para los 7 días de esa SE.</p></div>', unsafe_allow_html=True)

    st.markdown('<div style="background:#fff;border:1px solid #dde3ed;border-radius:10px;padding:24px;margin-bottom:16px;"><div style="font-size:16px;font-weight:600;color:#0369a1;margin-bottom:12px;">Cómo interpretar los resultados</div><p style="color:#374151;font-size:14px;line-height:1.7;margin:0;">El desglose etiológico muestra la distribución proyectada por causa respiratoria (Influenza, Neumonía, IRA, Bronquitis/Bronquiolitis, Crisis Obstructiva Bronquial, COVID-19). El análisis de vulnerabilidad etaria permite identificar los grupos poblacionales de mayor riesgo para la semana proyectada, orientando la asignación diferenciada de recursos pediátricos y geriátricos.</p></div>', unsafe_allow_html=True)

    st.markdown('<div style="background:#fff;border:1px solid #dde3ed;border-left:3px solid #0369a1;border-radius:10px;padding:20px 24px;margin-bottom:16px;"><div style="font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:#5a6b82;font-weight:600;margin-bottom:8px;">Desarrollado por</div><p style="color:#1a2942;font-size:14px;font-weight:500;margin:0 0 4px 0;">TM Eduardo Rojas Maturana · Dr. TM Neftalí Guzmán Oyarzo</p><p style="color:#5a6b82;font-size:12px;margin:0;">Facultad de Ciencias de la Salud, Universidad Católica de Temuco — Laboratorio de Investigación en Salud de Precisión</p></div>', unsafe_allow_html=True)

st.markdown(f'<div style="margin-top:24px;padding-top:14px;border-top:1px solid #dde3ed;font-size:11px;color:#5a6b82;">{APP_NAME} v{APP_VERSION} — Estimación de Demanda de Urgencias</div>', unsafe_allow_html=True)
