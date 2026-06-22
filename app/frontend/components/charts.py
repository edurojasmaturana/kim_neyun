"""
Modulo de graficas Plotly para KIM-NEYUN
"""

import plotly.graph_objects as go
import pandas as pd
from config import THEME

_LAYOUT_BASE = dict(
    font=dict(family="Inter, Segoe UI, sans-serif", color=THEME["text"]),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=16, r=16, t=48, b=16),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.05,
        xanchor="left",
        x=0,
        font=dict(size=12),
        bgcolor="rgba(0,0,0,0)",
        borderwidth=0,
        itemsizing="constant",
        tracegroupgap=4,
    ),
    xaxis=dict(
        gridcolor=THEME["border"],
        linecolor=THEME["border"],
        tickfont=dict(size=11),
        tickangle=-30,
        showspikes=True,
        spikethickness=1,
        spikecolor=THEME["text_muted"],
        spikedash="dot",
    ),
    yaxis=dict(
        gridcolor=THEME["border"],
        linecolor=THEME["border"],
        tickfont=dict(size=11),
        showspikes=True,
        spikethickness=1,
        spikecolor=THEME["text_muted"],
    ),
    hoverlabel=dict(
        bgcolor=THEME["surface"],
        bordercolor=THEME["border"],
        font_size=13,
        namelength=-1,
    ),
    hovermode="x unified",
)

_CONFIG = {
    "displayModeBar": True,
    "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
    "displaylogo": False,
    "toImageButtonOptions": {"format": "png", "scale": 2},
    "scrollZoom": True,
}


def prediction_line_chart(predictions, title="Prediccion de demanda asistencial", show_confidence=True):
    if not predictions:
        return _empty_chart("Sin datos de prediccion disponibles")
    df = pd.DataFrame(predictions)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    fig = go.Figure()

    if show_confidence and "confidence" in df.columns:
        margin = df["predicted_cases"] * (1 - df["confidence"])
        fig.add_trace(go.Scatter(
            x=pd.concat([df["date"], df["date"][::-1]]),
            y=pd.concat([df["predicted_cases"] + margin, (df["predicted_cases"] - margin)[::-1]]),
            fill="toself",
            fillcolor="rgba(45,125,210,0.12)",
            line=dict(color="rgba(0,0,0,0)"),
            name="Intervalo de confianza",
            hoverinfo="skip",
            showlegend=True,
        ))

    fig.add_trace(go.Scatter(
        x=df["date"],
        y=df["predicted_cases"],
        mode="lines+markers",
        name="Casos proyectados",
        line=dict(color=THEME["blue_light"], width=2.5, shape="spline", smoothing=0.6),
        marker=dict(
            size=6,
            color=THEME["blue_light"],
            line=dict(color=THEME["surface"], width=2),
            symbol="circle",
        ),
        hovertemplate="<b>%{x|%d %b %Y}</b><br>Casos: <b>%{y:,}</b><extra></extra>",
    ))

    # Linea de promedio
    avg = int(df["predicted_cases"].mean())
    fig.add_hline(
        y=avg,
        line_dash="dash",
        line_color=THEME["text_muted"],
        line_width=1,
        annotation_text=f"Promedio: {avg:,}",
        annotation_position="right",
        annotation_font_size=11,
        annotation_font_color=THEME["text_muted"],
    )

    layout = {
        **_LAYOUT_BASE,
        "title": dict(text=title, font=dict(size=15, color=THEME["navy"]), x=0, pad=dict(b=12)),
        "height": 400,
        "legend": dict(
            orientation="h",
            yanchor="top",
            y=-0.18,
            xanchor="left",
            x=0,
            font=dict(size=12),
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
        ),
        "margin": dict(l=16, r=16, t=48, b=64),
    }
    fig.update_layout(**layout)
    return fig


def alerts_distribution_chart(alerts):
    if not alerts:
        return _empty_chart("Sin alertas activas")
    counts = {"Critico": 0, "Moderado": 0, "Normal": 0}
    colors = [THEME["red"], THEME["amber"], THEME["green"]]
    for a in alerts:
        level = a.get("level", "VERDE")
        if level == "ROJO":
            counts["Critico"] += 1
        elif level == "AMARILLO":
            counts["Moderado"] += 1
        else:
            counts["Normal"] += 1
    total = sum(counts.values())
    fig = go.Figure(go.Pie(
        labels=list(counts.keys()),
        values=list(counts.values()),
        hole=0.62,
        marker=dict(
            colors=colors,
            line=dict(color=THEME["surface"], width=3),
        ),
        textinfo="label+percent",
        textposition="outside",
        textfont=dict(size=12),
        pull=[0.04, 0.04, 0.04],
        hovertemplate="<b>%{label}</b><br>%{value} alertas (%{percent})<extra></extra>",
    ))
    fig.update_layout(
        **{k: v for k, v in _LAYOUT_BASE.items() if k not in ("xaxis", "yaxis", "hovermode", "legend", "margin")},
        title=dict(text="Distribucion de alertas", font=dict(size=15, color=THEME["navy"]), x=0),
        annotations=[dict(
            text=f"<b>{total}</b><br>alertas",
            x=0.5, y=0.5,
            font=dict(size=16, color=THEME["navy"]),
            showarrow=False,
        )],
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.15,
            xanchor="center",
            x=0.5,
            font=dict(size=12),
        ),
        height=320,
        margin=dict(l=16, r=16, t=48, b=48),
    )
    return fig


def multi_pathology_chart(all_predictions, title="Comparativa por patologia"):
    if not all_predictions:
        return _empty_chart("Sin datos para comparar")
    palette = [THEME["blue_light"], THEME["red"], THEME["amber"], THEME["green"], THEME["teal"], THEME["blue"]]
    fig = go.Figure()
    for i, (pathology, preds) in enumerate(all_predictions.items()):
        if not preds:
            continue
        df = pd.DataFrame(preds)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")
        fig.add_trace(go.Scatter(
            x=df["date"],
            y=df["predicted_cases"],
            mode="lines",
            name=pathology,
            line=dict(color=palette[i % len(palette)], width=2, shape="spline", smoothing=0.5),
            hovertemplate=f"<b>{pathology}</b>: %{{y:,}} casos<extra></extra>",
        ))
    layout = {
        **_LAYOUT_BASE,
        "title": dict(text=title, font=dict(size=15, color=THEME["navy"]), x=0),
        "height": 380,
        "legend": dict(
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02,
            font=dict(size=11),
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor=THEME["border"],
            borderwidth=1,
        ),
        "margin": dict(l=16, r=140, t=48, b=16),
    }
    fig.update_layout(**layout)
    return fig


def trend_bar_chart(predictions, title="Casos proyectados por semana"):
    if not predictions:
        return _empty_chart("Sin datos")
    df = pd.DataFrame(predictions)
    df["date"] = pd.to_datetime(df["date"])
    df["week"] = df["date"].dt.to_period("W").dt.start_time
    weekly = df.groupby("week")["predicted_cases"].sum().reset_index()
    fig = go.Figure(go.Bar(
        x=weekly["week"],
        y=weekly["predicted_cases"],
        marker=dict(
            color=weekly["predicted_cases"],
            colorscale=[[0, THEME["teal"]], [0.5, THEME["blue_light"]], [1, THEME["blue"]]],
            line=dict(color="rgba(0,0,0,0)"),
            cornerradius=4,
        ),
        hovertemplate="<b>Semana %{x|%d %b}</b><br>%{y:,} casos<extra></extra>",
        text=weekly["predicted_cases"].apply(lambda x: f"{x:,}"),
        textposition="outside",
        textfont=dict(size=10),
    ))
    layout = {
        **_LAYOUT_BASE,
        "title": dict(text=title, font=dict(size=15, color=THEME["navy"]), x=0),
        "height": 380,
        "hovermode": "x",
        "showlegend": False,
    }
    fig.update_layout(**layout)
    return fig


def occupancy_gauge(value, title="Ocupacion proyectada"):
    bar_color = THEME["red"] if value >= 80 else THEME["amber"] if value >= 50 else THEME["green"]
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=value,
        delta=dict(reference=50, suffix="%", font=dict(size=14)),
        number=dict(suffix="%", font=dict(size=28, color=THEME["navy"])),
        gauge=dict(
            axis=dict(range=[0, 100], tickwidth=1, tickcolor=THEME["text_muted"], tickfont=dict(size=10)),
            bar=dict(color=bar_color, thickness=0.7),
            bgcolor=THEME["bg"],
            steps=[
                dict(range=[0, 50],   color="rgba(5,150,105,0.13)"),
                dict(range=[50, 80],  color="rgba(217,119,6,0.13)"),
                dict(range=[80, 100], color="rgba(192,57,43,0.13)"),
            ],
            threshold=dict(line=dict(color=THEME["red"], width=2), thickness=0.75, value=80),
        ),
        title=dict(text=title, font=dict(size=13, color=THEME["text_muted"])),
    ))
    fig.update_layout(
        **{k: v for k, v in _LAYOUT_BASE.items() if k not in ("xaxis", "yaxis", "legend", "hovermode")},
        height=240,
        margin=dict(l=20, r=20, t=48, b=10),
    )
    return fig


def _empty_chart(message):
    fig = go.Figure()
    fig.add_annotation(
        text=message, xref="paper", yref="paper",
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=14, color=THEME["text_muted"]),
    )
    fig.update_layout(
        **{k: v for k, v in _LAYOUT_BASE.items() if k not in ("xaxis", "yaxis")},
        height=250,
    )
    return fig


def get_plotly_config():
    return _CONFIG
