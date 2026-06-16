"""Semáforo de alerta de 3 niveles (NORMAL / MODERADO / CRITICO) por centro.

El umbral es relativo al propio histórico semanal de cada centro: un volumen
"crítico" en un SAPU chico no es comparable al de un hospital de alta complejidad.
Se derivan dos cortes por percentiles del total semanal histórico del centro:

- total >= percentil crítico  -> CRITICO
- total >= percentil moderado -> MODERADO
- resto                       -> NORMAL

Si el centro no tiene suficiente historia (`< ALERTA_MIN_SEMANAS`), se cae al
umbral global `ALERTA_THRESHOLD` como respaldo.

No depende de torch ni de los artefactos del modelo: es una clasificación simple
sobre el DataFrame histórico que ya carga el job batch.
"""

import numpy as np

from . import config
from .catalog import TODOS_TARGETS

NIVEL_NORMAL = "NORMAL"
NIVEL_MODERADO = "MODERADO"
NIVEL_CRITICO = "CRITICO"

# Mismas columnas de causa que suma el motor para el Total (ver engine.predecir_semana).
_CAUSAS = [t for t in TODOS_TARGETS if t.startswith("Cause_")]


def _totales_semanales_historicos(df_historia, hospital, anio_ref, semana_ref):
    """Serie de totales semanales (suma de causas) del centro, anteriores a la
    semana de referencia. Mismo recorte temporal que `engine.predecir_semana`."""
    df = df_historia[df_historia["EstablecimientoGlosa"] == hospital]
    df = df[
        (df["Anio"] < anio_ref)
        | ((df["Anio"] == anio_ref) & (df["SemanaEstadistica"] < semana_ref))
    ]
    causas = [c for c in _CAUSAS if c in df.columns]
    if df.empty or not causas:
        return np.array([])
    return df[causas].fillna(0).sum(axis=1).to_numpy()


def umbrales_centro(df_historia, hospital, anio_ref, semana_ref):
    """Devuelve `(umbral_moderado, umbral_critico)` por centro, o `None` si no hay
    historia suficiente (en cuyo caso `clasificar` usa el respaldo global)."""
    totales = _totales_semanales_historicos(df_historia, hospital, anio_ref, semana_ref)
    if totales.size < config.ALERTA_MIN_SEMANAS:
        return None
    return (
        float(np.percentile(totales, config.ALERTA_PCT_MODERADO)),
        float(np.percentile(totales, config.ALERTA_PCT_CRITICO)),
    )


def clasificar(total, umbrales):
    """Clasifica `total` en NORMAL / MODERADO / CRITICO.

    `umbrales` = `(moderado, critico)` del centro, o `None` para usar el respaldo
    global (crítico = ALERTA_THRESHOLD; moderado = 70% de ese valor).
    """
    if umbrales is None:
        critico = config.ALERTA_THRESHOLD
        moderado = 0.7 * critico
    else:
        moderado, critico = umbrales
    if total >= critico:
        return NIVEL_CRITICO
    if total >= moderado:
        return NIVEL_MODERADO
    return NIVEL_NORMAL
