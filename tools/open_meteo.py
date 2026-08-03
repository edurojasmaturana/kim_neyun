"""
tools/open_meteo.py — Módulo 2b: fallback Open-Meteo (opcional).

Open-Meteo es un fallback ambiental con licencia CC BY-SA 4.0 (comercial
permitido con atribución + share-alike). Se usa solo si SINCA no cubre
suficientes días (config: open_meteo.fallback_threshold).

Reproduce las mismas agregaciones que SINCA:
- temperature_2m_max → Temperatura_Max (sin corrección de sensor)
- wind_speed_10m_max → Vel_Max
- precipitation_sum → precipitaciones_Total
- surface_pressure_mean → presion_Avg

API doc: https://open-meteo.com/en/docs/historical-weather-api

Referencia spec: PIPELINE_SPEC.md §3.6 (notas de fallback).
"""
from __future__ import annotations

import logging
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import requests

from .config import Config

log = logging.getLogger(__name__)

OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


class OpenMeteoFetcher:
    """Descarga datos diarios de Open-Meteo y los agrega a semanal ISO."""

    def __init__(self, cfg: Config):
        self.cfg = cfg

    # ------------------------------------------------------------------
    # Descarga diaria
    # ------------------------------------------------------------------
    def fetch_daily(self,
                    start_date: str,
                    end_date: str) -> pd.DataFrame:
        """
        Descarga datos diarios Open-Meteo para las coordenadas del estudio.

        Devuelve DataFrame con columnas ['date', *variables_diarias].
        """
        om = self.cfg.open_meteo
        params = {
            'latitude': om.lat,
            'longitude': om.lon,
            'start_date': start_date,
            'end_date': end_date,
            'daily': ','.join(om.variables_diarias),
            'timezone': 'America/Santiago',
        }
        log.info("OpenMeteo: descargando %s → %s para (%.4f, %.4f)",
                 start_date, end_date, om.lat, om.lon)
        r = requests.get(OPEN_METEO_ARCHIVE_URL, params=params, timeout=120)
        r.raise_for_status()
        data = r.json()

        if 'daily' not in data:
            raise RuntimeError(f"OpenMeteo: respuesta sin 'daily'. Keys: {list(data.keys())}")

        df = pd.DataFrame(data['daily'])
        df['date'] = pd.to_datetime(df['time'])
        log.info("OpenMeteo: %d días, %d variables", len(df), len(om.variables_diarias))
        return df

    # ------------------------------------------------------------------
    # Agregación semanal ISO (alineada con SINCA)
    # ------------------------------------------------------------------
    def to_weekly_iso(self, df_daily: pd.DataFrame) -> pd.DataFrame:
        """
        Agrega datos diarios a semanal ISO (Anio, SemanaEstadistica).

        Reglas (alineadas con procesar_sinca del notebook):
        - temperature_2m_max → mean + max → Temperatura_Avg, Temperatura_Max
        - wind_speed_10m_max → mean + max → Vel_Avg, Vel_Max
        - precipitation_sum → sum → precipitaciones_Total
        - surface_pressure_mean → mean + max → presion_Avg, presion_Max
        """
        iso = df_daily['date'].dt.isocalendar()
        df = df_daily.copy()
        df['Anio'] = iso.year
        df['SemanaEstadistica'] = iso.week

        agg_specs = {
            'temperature_2m_max':   ('Temperatura',     'mean_max'),
            'wind_speed_10m_max':   ('Vel',             'mean_max'),
            'precipitation_sum':    ('precipitaciones', 'sum'),
            'surface_pressure_mean':('presion',         'mean_max'),
        }

        out_frames = []
        for var_in, (nombre, agg) in agg_specs.items():
            if var_in not in df.columns:
                log.warning("OpenMeteo: variable %s no está en la respuesta. Saltando.", var_in)
                continue
            if agg == 'mean_max':
                res = df.groupby(['Anio', 'SemanaEstadistica'])[var_in].agg(['mean', 'max']).reset_index()
                res.columns = ['Anio', 'SemanaEstadistica', f'{nombre}_Avg', f'{nombre}_Max']
            elif agg == 'sum':
                res = df.groupby(['Anio', 'SemanaEstadistica'])[var_in].sum().reset_index()
                res.columns = ['Anio', 'SemanaEstadistica', f'{nombre}_Total']
            out_frames.append(res)

        if not out_frames:
            raise RuntimeError("OpenMeteo: ninguna variable pudo agregarse.")

        from functools import reduce
        df_env = reduce(
            lambda l, r: pd.merge(l, r, on=['Anio', 'SemanaEstadistica'], how='outer'),
            out_frames
        )
        df_env = df_env.sort_values(['Anio', 'SemanaEstadistica']).reset_index(drop=True)
        log.info("OpenMeteo: weekly aggregated shape=%s", df_env.shape)
        return df_env

    # ------------------------------------------------------------------
    # Run completo
    # ------------------------------------------------------------------
    def run(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Descarga + agregación semanal. Devuelve df_env_final equivalente."""
        df_daily = self.fetch_daily(start_date, end_date)
        return self.to_weekly_iso(df_daily)
