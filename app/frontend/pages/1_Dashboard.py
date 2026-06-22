import streamlit as st
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
import sys, os, base64

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if "token" not in st.session_state or not st.session_state.token:
    st.switch_page("pages/login.py")

from config import (
    PAGE_CONFIG, GLOBAL_CSS, APP_NAME, APP_DESCRIPTION, APP_VERSION,
    TRADUCCION_CAUSAS, TRADUCCION_EDADES,
)
from components.api_client import fetch_prediction, fetch_hospitales, invalidate_cache, render_connection_badge
from components.charts import get_plotly_config
from utils import initialize_session_state


def get_semana_epi(d):
    """Calcula la semana epidemiologica CDC/MINSAL (comienza el domingo)."""
    dia_semana = d.weekday()
    dias_desde_domingo = (dia_semana + 1) % 7
    domingo = d - timedelta(days=dias_desde_domingo)
    inicio_anio = date(domingo.year, 1, 1)
    primer_domingo = inicio_anio - timedelta(days=(inicio_anio.weekday() + 1) % 7)
    se = ((domingo - primer_domingo).days // 7) + 1
    return domingo.year, se, domingo


def traducir_causa(clave):
    """Las claves de la API vienen como 'Cause_<nombre>' o '<nombre>' directo.
    El catalogo guarda las traducciones sin el prefijo 'Cause_'."""
    clave_limpia = clave.replace("Cause_", "")
    return TRADUCCION_CAUSAS.get(clave_limpia, clave_limpia.replace("_", " "))


def traducir_edad(clave):
    """Las claves de edad de la API vienen como '65oMas', 'Menor1Anio', etc.,
    coincidiendo con las llaves de TRADUCCION_EDADES del catalogo."""
    return TRADUCCION_EDADES.get(clave, clave)


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

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        f'<div style="padding:16px 0 20px 0;border-bottom:1px solid rgba(255,255,255,.12);margin-bottom:20px;">'
        f'<div style="font-size:20px;font-weight:700;color:#fff;">{APP_NAME}</div>'
        f'<div style="font-size:11px;color:rgba(255,255,255,.5);margin-top:3px;">{APP_DESCRIPTION}</div>'
        f'<div style="font-size:10px;color:rgba(255,255,255,.3);margin-top:6px;">v{APP_VERSION}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    backend_ok = render_connection_badge()

    st.markdown(
        '<div style="font-size:10px;text-transform:uppercase;letter-spacing:.08em;'
        'color:rgba(255,255,255,.4);margin-bottom:12px;">Parametros</div>',
        unsafe_allow_html=True,
    )

    token = st.session_state.get("token")
    hospitales_result = fetch_hospitales(token)
    hospitales_list = hospitales_result["data"].get("hospitales", [])

    if not hospitales_list:
        st.error("No se pudieron cargar los centros asistenciales.")
        st.stop()

    st.markdown(
        '<div style="font-size:9px;color:rgba(255,255,255,.6);margin-bottom:3px;'
        'text-transform:uppercase;letter-spacing:.05em;">Establecimiento</div>',
        unsafe_allow_html=True,
    )
    selected_hospital = st.selectbox(
        "Establecimiento",
        hospitales_list,
        index=0,
        label_visibility="collapsed",
    )

    st.markdown(
        '<div style="font-size:9px;color:rgba(255,255,255,.6);margin-top:10px;margin-bottom:3px;'
        'text-transform:uppercase;letter-spacing:.05em;">Fecha de referencia</div>',
        unsafe_allow_html=True,
    )
    selected_date = st.date_input(
        "Fecha",
        value=date.today(),
        min_value=date(2024, 1, 1),
        max_value=date.today() + timedelta(days=30),
        label_visibility="collapsed",
        format="DD/MM/YYYY",
    )

    iso_year, iso_week, domingo_se = get_semana_epi(selected_date)

    st.markdown(
        f'<div style="background:rgba(255,255,255,.1);border-radius:6px;padding:7px 10px;'
        f'margin-top:8px;font-size:11px;color:rgba(255,255,255,.8);">'
        f'SE <strong>{iso_week}</strong> - {iso_year}'
        f'<br><span style="font-size:10px;opacity:.7;">Inicio: domingo {domingo_se.strftime("%d/%m/%Y")}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.markdown("<hr>", unsafe_allow_html=True)

    if st.button("Actualizar datos", use_container_width=True):
        invalidate_cache()
        st.session_state.last_refresh = datetime.now()
        st.rerun()

    last_refresh = st.session_state.get("last_refresh", datetime.now())
    st.markdown(
        f'<div style="font-size:10px;color:rgba(255,255,255,.35);margin-top:8px;">'
        f'Actualizado: {last_refresh.strftime("%H:%M:%S")}</div>',
        unsafe_allow_html=True,
    )

# ── CARGA DE DATOS ────────────────────────────────────────────────────────────
token = st.session_state.get("token")
fecha_referencia = selected_date.strftime("%Y-%m-%d")

with st.spinner("Consultando motor predictivo HZF..."):
    pred_result = fetch_prediction(
        token=token,
        establecimiento=selected_hospital,
        fecha_referencia=fecha_referencia,
    )

if not pred_result["success"]:
    error_msg = pred_result["error"]
    if "404" in str(error_msg) or "No hay predicción" in str(error_msg):
        st.warning(
            f"No hay predicción precomputada para la semana del "
            f"{domingo_se.strftime('%d/%m/%Y')} en este centro. "
            f"El backfill táctico cubre un rango limitado de semanas; "
            f"prueba con la semana actual."
        )
    else:
        st.error(f"Error al obtener predicción: {error_msg}")
    st.stop()

pred_data    = pred_result["data"]
semana_epi   = pred_data.get("semana_epi", iso_week)
anio         = pred_data.get("año", iso_year)
estimaciones = pred_data.get("estimaciones", {})
causas       = estimaciones.get("Causas", {})
edades       = estimaciones.get("Edades", {})
total_casos  = estimaciones.get("Total", 0)
temperatura  = pred_data.get("temperatura_referencia")
nivel_alerta = pred_data.get("nivel_alerta", "NORMAL")
temp_str     = f"{round(temperatura, 1)} °C" if temperatura is not None else "N/D"
color_alerta = (
    "#e53e3e" if nivel_alerta.upper() == "CRITICO"
    else "#d97706" if nivel_alerta.upper() == "MODERADO"
    else "#059669"
)

# ── HEADER ────────────────────────────────────────────────────────────────────
dias_es  = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
meses_es = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
            "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
fecha_str = (
    f"{dias_es[selected_date.weekday()]} "
    f"{selected_date.day} de "
    f"{meses_es[selected_date.month - 1]} de "
    f"{selected_date.year}"
)

logo_html = (
    f'<img src="{LOGO_UCT}" style="position:absolute;top:16px;right:20px;'
    f'height:70px;opacity:0.95;filter:brightness(0) invert(1);" alt="UCTemuco"/>'
    if LOGO_UCT else ""
)

st.markdown(
    f'<div style="background:linear-gradient(135deg,#0369a1 0%,#0ea5e9 100%);'
    f'border-radius:12px;padding:20px 24px;margin-bottom:20px;color:#fff;position:relative;">'
    f'<div style="font-size:10px;text-transform:uppercase;letter-spacing:.1em;opacity:.65;margin-bottom:5px;">'
    f'Sistema predictivo de demanda asistencial</div>'
    f'<div style="font-size:20px;font-weight:700;line-height:1.2;margin-bottom:3px;">'
    f'Consultas Respiratorias — {selected_hospital}</div>'
    f'<div style="font-size:12px;opacity:.7;">SE {semana_epi} — {fecha_str}</div>'
    f'{logo_html}</div>',
    unsafe_allow_html=True,
)

# ── KPIs ──────────────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(
        f'<div style="background:#fff;border:1px solid #dde3ed;border-top:3px solid #0ea5e9;'
        f'border-radius:8px;padding:12px 14px;">'
        f'<div style="font-size:9px;text-transform:uppercase;letter-spacing:.06em;color:#5a6b82;margin-bottom:4px;">Total consultas respiratorias</div>'
        f'<div style="font-size:28px;font-weight:600;color:#0369a1;">{int(total_casos)}</div>'
        f'<div style="font-size:11px;color:#5a6b82;margin-top:2px;">suma de todas las causas</div></div>',
        unsafe_allow_html=True,
    )

with col2:
    st.markdown(
        f'<div style="background:#fff;border:1px solid #dde3ed;border-top:3px solid #0d9488;'
        f'border-radius:8px;padding:12px 14px;">'
        f'<div style="font-size:9px;text-transform:uppercase;letter-spacing:.06em;color:#5a6b82;margin-bottom:4px;">Semana epidemiológica</div>'
        f'<div style="font-size:28px;font-weight:600;color:#0369a1;">SE {semana_epi}</div>'
        f'<div style="font-size:11px;color:#5a6b82;margin-top:2px;">año {anio}</div></div>',
        unsafe_allow_html=True,
    )

with col3:
    st.markdown(
        f'<div style="background:#fff;border:1px solid #dde3ed;border-top:3px solid #d97706;'
        f'border-radius:8px;padding:12px 14px;">'
        f'<div style="font-size:9px;text-transform:uppercase;letter-spacing:.06em;color:#5a6b82;margin-bottom:4px;">Temperatura referencia</div>'
        f'<div style="font-size:28px;font-weight:600;color:#0369a1;">{temp_str}</div>'
        f'<div style="font-size:11px;color:#5a6b82;margin-top:2px;">estresor ambiental</div></div>',
        unsafe_allow_html=True,
    )

with col4:
    st.markdown(
        f'<div style="background:#fff;border:1px solid #dde3ed;border-top:3px solid {color_alerta};'
        f'border-radius:8px;padding:12px 14px;">'
        f'<div style="font-size:9px;text-transform:uppercase;letter-spacing:.06em;color:#5a6b82;margin-bottom:4px;">Nivel de alerta</div>'
        f'<div style="font-size:22px;font-weight:600;color:{color_alerta};">{nivel_alerta.capitalize()}</div>'
        f'<div style="font-size:11px;color:#5a6b82;margin-top:2px;">basado en volumen total</div></div>',
        unsafe_allow_html=True,
    )

st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)

# ── GRÁFICOS ──────────────────────────────────────────────────────────────────
col_left, col_right = st.columns([3, 2], gap="medium")

with col_left:
    if causas:
        causas_ord = sorted(causas.items(), key=lambda x: x[1], reverse=True)
        nombres = [traducir_causa(k) for k, _ in causas_ord]
        valores = [v for _, v in causas_ord]
        paleta  = ["#0369a1", "#0ea5e9", "#38bdf8", "#7dd3fc", "#bae6fd", "#e0f2fe", "#cffafe", "#f0f9ff"]

        fig = go.Figure(go.Bar(
            x=valores, y=nombres, orientation="h",
            marker=dict(color=paleta[:len(nombres)], line=dict(color="rgba(0,0,0,0)")),
            text=[str(int(v)) for v in valores],
            textposition="outside",
            textfont=dict(size=11, color="#0369a1"),
            hovertemplate="<b>%{y}</b><br>%{x:,.0f} consultas<extra></extra>",
        ))
        fig.update_layout(
            title=dict(text=f"¿Por qué consultarán? — SE {semana_epi}", font=dict(size=13, color="#0369a1"), x=0),
            font=dict(family="Inter, sans-serif", color="#5a6b82"),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=12, r=60, t=44, b=12),
            xaxis=dict(gridcolor="#e0f2fe", linecolor="#dde3ed", tickfont=dict(size=10), title="Consultas estimadas"),
            yaxis=dict(linecolor="#dde3ed", tickfont=dict(size=11), autorange="reversed"),
            hoverlabel=dict(bgcolor="#fff", bordercolor="#dde3ed", font_size=12),
            height=320, showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True, config=get_plotly_config())
    else:
        st.info("Sin desglose de causas disponible para esta semana.")

with col_right:
    edades_ord = sorted(edades.items(), key=lambda x: x[1], reverse=True) if edades else []

    if edades_ord:
        nombres_e = [traducir_edad(k) for k, _ in edades_ord]
        valores_e = [v for _, v in edades_ord]
        total_e   = sum(valores_e) or 1
        pcts      = [round((v / total_e) * 100) for v in valores_e]
        paleta_e  = ["#0369a1", "#0ea5e9", "#38bdf8", "#7dd3fc", "#bae6fd"]

        fig2 = go.Figure(go.Bar(
            x=valores_e, y=nombres_e, orientation="h",
            marker=dict(
                color=[paleta_e[i % len(paleta_e)] for i in range(len(nombres_e))],
                line=dict(color="rgba(0,0,0,0)"),
            ),
            text=[f"{int(v)} ({p}%)" for v, p in zip(valores_e, pcts)],
            textposition="outside",
            textfont=dict(size=10, color="#0369a1"),
            hovertemplate="<b>%{y}</b><br>%{x:,.0f} consultas<extra></extra>",
        ))
        fig2.update_layout(
            title=dict(text="Vulnerabilidad etaria", font=dict(size=13, color="#0369a1"), x=0),
            font=dict(family="Inter, sans-serif", color="#5a6b82"),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=12, r=70, t=44, b=12),
            xaxis=dict(gridcolor="#e0f2fe", linecolor="#dde3ed", tickfont=dict(size=10), title="Consultas estimadas"),
            yaxis=dict(linecolor="#dde3ed", tickfont=dict(size=11), autorange="reversed"),
            hoverlabel=dict(bgcolor="#fff", bordercolor="#dde3ed", font_size=12),
            height=320, showlegend=False,
        )
        st.plotly_chart(fig2, use_container_width=True, config=get_plotly_config())
    else:
        st.markdown(
            '<div style="background:#fff;border:1px solid #dde3ed;border-radius:8px;'
            'padding:40px;text-align:center;color:#5a6b82;font-size:12px;">'
            'Sin desglose etario disponible para este centro.'
            '</div>',
            unsafe_allow_html=True,
        )

# ── BADGE ALERTA ──────────────────────────────────────────────────────────────
st.markdown(
    f'<div style="text-align:center;margin:16px 0;">'
    f'<span style="background:{color_alerta}18;border:1px solid {color_alerta};'
    f'border-radius:6px;padding:8px 20px;font-size:13px;font-weight:500;color:{color_alerta};">'
    f'Nivel de alerta: {nivel_alerta.capitalize()} — SE {semana_epi} / {anio}'
    f'</span></div>',
    unsafe_allow_html=True,
)

# ── FOOTER ────────────────────────────────────────────────────────────────────
st.markdown(
    f'<div style="margin-top:24px;padding-top:14px;border-top:1px solid #dde3ed;'
    f'font-size:11px;color:#5a6b82;display:flex;justify-content:space-between;">'
    f'<span>{APP_NAME} v{APP_VERSION} — Sistema Predictivo de Demanda Asistencial</span>'
    f'<span>{"Conectado al backend" if backend_ok else "Sin conexión al backend"}</span>'
    f'</div>',
    unsafe_allow_html=True,
)
