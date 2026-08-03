"""
tools/features.py — Módulo 3: merge + lags (réplica 1:1 del notebook).

Reproduce celda 46 (final) del notebook RespiratorIA2.ipynb:
- Inner join df_aglomerado + df_env_final sobre (Anio, SemanaEstadistica).
- Filtro Anio < descartar_anios_mayores_a + 1.
- Creación de Lag1, Lag2 sobre las 12 columnas ambientales.
- dropna (elimina 2 primeras semanas por Lag2).

Referencia spec: PIPELINE_SPEC.md §4.
"""
from __future__ import annotations

import logging
from typing import List

import pandas as pd

from .config import Config

log = logging.getLogger(__name__)


def build_features(df_aglomerado: pd.DataFrame,
                   df_env_final: pd.DataFrame,
                   cfg: Config) -> pd.DataFrame:
    """
    Construye df_modelos a partir de salud (aglomerado) + ambiente.

    Réplica 1:1 de celda 46 (final) del notebook:
        df_ml = pd.merge(df_aglomerado, df_env_final, on=['Anio', 'SemanaEstadistica'], how='inner')
        df_ml = df_ml[df_ml['Anio'] < 2026].sort_values(...).reset_index(drop=True)
        for col in cols_env:
            df_ml[f'{col}_Lag1'] = df_ml[col].shift(1)
            df_ml[f'{col}_Lag2'] = df_ml[col].shift(2)
        df_modelos = df_ml.dropna().reset_index(drop=True)

    Parámetros
    ----------
    df_aglomerado : DataFrame nivel ciudad (salud), 13 columnas numéricas + 2 temporales.
    df_env_final  : DataFrame ambiental con columnas {nombre}_{Avg,Max,Total}.
    cfg           : Config.

    Devuelve
    --------
    df_modelos : DataFrame con shape aprox. (N_semanas - 2, 51 columnas):
                 2 temporales + 13 salud + 12 ambientales base + 24 lags.
    """
    lag_orders: List[int] = cfg.features.lag_orders
    dropna: bool = cfg.features.dropna
    descartar = cfg.study.descartar_anios_mayores_a

    # 1. Inner join (celda 46)
    df_ml = pd.merge(
        df_aglomerado, df_env_final,
        on=['Anio', 'SemanaEstadistica'],
        how='inner'
    )

    # 2. Filtro años + orden (celda 46)
    df_ml = df_ml[df_ml['Anio'] <= descartar].copy()
    df_ml = df_ml.sort_values(['Anio', 'SemanaEstadistica']).reset_index(drop=True)

    # 3. Lags sobre ambientales (celda 46)
    #    Solo se hace lag sobre cols_env (12 columnas ambientales base),
    #    NO sobre salud.
    cols_env = [c for c in df_env_final.columns
                if c not in ('Anio', 'SemanaEstadistica')]
    for col in cols_env:
        for lag in lag_orders:
            df_ml[f'{col}_Lag{lag}'] = df_ml[col].shift(lag)

    # 4. dropna (celda 46)
    n_before = len(df_ml)
    if dropna:
        df_ml = df_ml.dropna().reset_index(drop=True)
    n_after = len(df_ml)
    log.info("Features: dropna eliminó %d filas (%d → %d)",
             n_before - n_after, n_before, n_after)

    # 5. Resumen
    n_lag_cols = sum(1 for c in df_ml.columns if '_Lag' in c)
    n_env_base = len(cols_env)
    log.info("Features: df_modelos shape=%s. Ambientales base=%d, lags=%d, total env=%d",
             df_ml.shape, n_env_base, n_lag_cols, n_env_base + n_lag_cols)
    return df_ml
