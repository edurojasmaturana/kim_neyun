"""
Configuración compartida para gráficos Plotly — KIM-NEYÜN
"""

_CONFIG = {
    "displayModeBar": True,
    "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
    "displaylogo": False,
    "toImageButtonOptions": {"format": "png", "scale": 2},
}


def get_plotly_config():
    """Configuración estándar de la toolbar de Plotly para todos los gráficos."""
    return _CONFIG
