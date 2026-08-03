"""
tools/sinca.py — Módulo 2a: extracción SINCA (estación Las Encinas, id=186).

- `limpiar_valor()` y `procesar_sinca_df()` son réplica literal del notebook.
- Agregación semanal ISO (Anio, SemanaEstadistica).
- Prioridad contaminantes: Registros validados > preliminares > no validados.
- Corrección sensor Temperatura (> 60 → /100).
- Outer join de las 7 fuentes ambientales.
- Estrategia faltantes: `report` (reportar, no imputar).

Modos de obtención (`sinca.mode` en config.yaml):
- `local_csv` (default, recomendado): lee los 7 CSVs descargados manualmente
  desde `https://sinca.mma.gob.cl/index.php/estacion/index/id/186` y dejados
  en `sinca.local_dir` (típicamente `data/raw/sinca/`). Es el modo más fiel al
  notebook original, que también usaba CSVs locales en Drive.
- `api` (fallback): intenta el endpoint `apub.tsca` de SINCA. **ALERTA 2026-07-31**:
  este endpoint está caído (HTTP 404) y el CGI actual solo renderiza GIFs
  server-side. Se mantiene por si SINCA revive en el futuro.

Referencia spec: PIPELINE_SPEC.md §3.
"""
from __future__ import annotations

import io
import logging
import os
from functools import reduce
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

from .config import Config

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Funciones del notebook (celda 46) — LITERAL, no modificar.
# ---------------------------------------------------------------------------

def limpiar_valor(x) -> float:
    """Convierte string con comas a float, manejando puntos de miles.

    Réplica literal de celda 46 / celda 19 del notebook.
    """
    if pd.isna(x):
        return np.nan
    try:
        return float(str(x).strip().replace('.', '').replace(',', '.'))
    except Exception:
        return np.nan


def procesar_sinca_df(df: pd.DataFrame,
                      nombre: str,
                      tipo: str = 'mean',
                      contaminante: bool = False,
                      es_temp: bool = False) -> pd.DataFrame:
    """
    Procesa un DataFrame SINCA ya leído (CSV o API) replicando celda 46.

    Parámetros
    ----------
    df : DataFrame crudo desde SINCA. Debe tener al menos una columna con
         'FECHA' en su nombre.
    nombre : nombre de variable de salida (ej. 'Monoxido', 'PM25').
    tipo : 'mean' (genera _Avg, _Max) o 'sum' (genera _Total).
    contaminante : si True, usa prioridad validados>preliminares>no-validados.
    es_temp : si True, aplica corrección sensor (valor>60 → /100).

    Devuelve
    --------
    DataFrame con columnas ['Anio', 'SemanaEstadistica', f'{nombre}_Avg',
    f'{nombre}_Max'] (o f'{nombre}_Total' si tipo='sum').
    """
    # 1. Columna fecha (primera que contenga 'FECHA' uppercase)
    col_fecha = [c for c in df.columns if 'FECHA' in c.upper()][0]

    # 2. Parse fecha YYMMDD (formato SINCA histórico)
    df['fecha_dt'] = pd.to_datetime(
        df[col_fecha].astype(str).str.zfill(6),
        format='%y%m%d', errors='coerce'
    )
    df = df.dropna(subset=['fecha_dt']).copy()

    # 3. ISO week (Anio, SemanaEstadistica)
    iso = df['fecha_dt'].dt.isocalendar()
    df['Anio'] = iso.year
    df['SemanaEstadistica'] = iso.week

    # 4. Valor
    if contaminante:
        valid_cols = [c for c in
                      ['Registros validados', 'Registros preliminares', 'Registros no validados']
                      if c in df.columns]
        for c in valid_cols:
            df[c] = df[c].apply(limpiar_valor)
        # Prioridad izquierda → derecha (bfill axis=1)
        df['valor'] = df[valid_cols].bfill(axis=1).iloc[:, 0]
    else:
        col_valor = [c for c in df.columns
                     if 'FECHA' not in c.upper()
                     and 'HORA' not in c.upper()
                     and 'fecha_dt' not in c][0]
        df['valor'] = df[col_valor].apply(limpiar_valor)
        if es_temp:
            df['valor'] = df['valor'].apply(lambda v: v / 100 if v > 60 else v)

    # 5. Agregación semanal
    if tipo == 'mean':
        res = df.groupby(['Anio', 'SemanaEstadistica'])['valor'].agg(['mean', 'max']).reset_index()
        res.columns = ['Anio', 'SemanaEstadistica', f'{nombre}_Avg', f'{nombre}_Max']
    elif tipo == 'sum':
        res = df.groupby(['Anio', 'SemanaEstadistica'])['valor'].sum().reset_index()
        res.columns = ['Anio', 'SemanaEstadistica', f'{nombre}_Total']
    else:
        raise ValueError(f"tipo debe ser 'mean' o 'sum', recibido: {tipo}")

    return res


# ---------------------------------------------------------------------------
# SINCAFetcher: descarga datos desde la API SINCA o lee CSV local.
# ---------------------------------------------------------------------------

# URL template SINCA — apub.tsca (servicio TSCA del MMA).
# Devuelve un CSV en formato SINCA estándar (FECHA, HORA, Registros...).
SINCA_URL_TEMPLATE = (
    "https://sinca.mma.gob.cl/cgi-bin/APUB-MMA/apub.tsca"
    "?tipo=QUERY&ind={param}&station={station_id}"
)

# Mapping agregación notebook → (tipo, contaminante, es_temp)
def _agg_to_tipo(agg: str) -> str:
    """Convierte 'mean_max' → 'mean', 'sum' → 'sum'."""
    if agg == 'mean_max':
        return 'mean'
    if agg == 'sum':
        return 'sum'
    raise ValueError(f"agregación desconocida: {agg}")


class SINCAFetcher:
    """Descarga datos SINCA por estación y parámetro, replica procesar_sinca().

    Modo `local_csv` (default): lee los 7 CSVs descargados manualmente desde
    `sinca.local_dir`. Es el modo fiel al notebook original.
    Modo `api`: intenta el endpoint `apub.tsca` (actualmente caído).
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.mode = getattr(cfg.sinca, 'mode', 'local_csv')
        self.local_dir = getattr(cfg.sinca, 'local_dir', os.path.join('data', 'raw', 'sinca'))
        self.station_id = cfg.sinca.station_id
        self.missing_strategy = cfg.sinca.missing_strategy
        self.missing_report: List[Dict] = []
        log.info("SINCA: modo=%s, local_dir=%s, station_id=%d",
                 self.mode, self.local_dir, self.station_id)

    # ------------------------------------------------------------------
    # Descarga de un parámetro
    # ------------------------------------------------------------------
    def _fetch_local_csv(self, nombre: str) -> Optional[pd.DataFrame]:
        """Lee CSV local desde `sinca.local_dir/{nombre}.csv`.

        Tolerante a variantes del nombre de archivo: acepta también
        `{nombre}.CSV` y, para PM25, el nombre histórico `PM2.5.csv`.
        """
        candidatos = [
            f"{nombre}.csv",
            f"{nombre}.CSV",
        ]
        # Alias históricos del notebook
        if nombre == 'PM25':
            candidatos += ['PM2.5.csv', 'PM2.5.CSV']

        for fname in candidatos:
            p = os.path.join(self.local_dir, fname)
            if os.path.exists(p):
                log.info("SINCA: leyendo CSV local %s", p)
                try:
                    return pd.read_csv(p, sep=None, engine='python')
                except Exception as e:
                    log.warning("SINCA: fallo leyendo %s: %s.", p, e)
                    return None
        log.warning("SINCA: no se encontró CSV local para '%s' en %s (buscado: %s)",
                    nombre, self.local_dir, candidatos)
        return None

    def _fetch_api(self, nombre: str, param: str) -> Optional[pd.DataFrame]:
        """Descarga CSV desde el endpoint `apub.tsca` de SINCA (fallback).

        ⚠️ ALERTA 2026-07-31: este endpoint está caído (HTTP 404). El CGI
        actual solo renderiza GIFs server-side. Se mantiene por si SINCA revive.
        """
        url = SINCA_URL_TEMPLATE.format(param=param, station_id=self.station_id)
        log.info("SINCA: descargando %s desde %s", nombre, url)
        try:
            r = requests.get(url, timeout=120, headers={"User-Agent": "RespiratorIA2/1.0"})
            r.raise_for_status()
            return pd.read_csv(io.StringIO(r.text), sep=None, engine='python')
        except Exception as e:
            log.error("SINCA: API falló para %s (%s). param=%s station=%d.",
                      nombre, e, param, self.station_id)
            return None

    def _fetch_csv(self, nombre: str, param: str) -> Optional[pd.DataFrame]:
        """
        Obtiene el DataFrame SINCA para (station, param) según `self.mode`.

        - `local_csv`: solo lee CSV local. Si no existe, registra y devuelve None.
        - `api`: intenta API primero; si falla, prueba CSV local como respaldo.
        """
        if self.mode == 'local_csv':
            return self._fetch_local_csv(nombre)
        # mode == 'api'
        df = self._fetch_api(nombre, param)
        if df is None or df.empty:
            log.info("SINCA: API falló para %s, intentando CSV local...", nombre)
            df = self._fetch_local_csv(nombre)
        return df

    # ------------------------------------------------------------------
    # Procesamiento de una fuente
    # ------------------------------------------------------------------
    def _process_one(self, spec: Dict) -> Optional[pd.DataFrame]:
        """Procesa una fuente (contaminante o meteorológica)."""
        nombre = spec['nombre']
        param = spec['param']
        agg = spec.get('agregacion', 'mean_max')
        corregir_sensor = spec.get('corregir_sensor', False)
        es_contaminante = spec.get('es_contaminante', False)
        # Heurística: PM* y CO son contaminantes
        if 'es_contaminante' not in spec:
            es_contaminante = param.upper() in ('CO', 'PM25', 'PM2.5', 'PM10', 'SO2', 'NO2', 'O3')

        tipo = _agg_to_tipo(agg)
        df_raw = self._fetch_csv(nombre, param)
        if df_raw is None or df_raw.empty:
            self.missing_report.append({
                'fuente': nombre, 'param': param, 'motivo': 'descarga_fallida'
            })
            return None

        try:
            res = procesar_sinca_df(
                df_raw, nombre=nombre, tipo=tipo,
                contaminante=es_contaminante, es_temp=corregir_sensor
            )
            log.info("SINCA: %s procesado. %d semanas, cols=%s",
                     nombre, len(res), list(res.columns))
            return res
        except Exception as e:
            log.error("SINCA: error procesando %s: %s", nombre, e)
            self.missing_report.append({
                'fuente': nombre, 'param': param, 'motivo': f'procesamiento: {e}'
            })
            return None

    # ------------------------------------------------------------------
    # Merge outer (celda 46)
    # ------------------------------------------------------------------
    def _merge_outer(self, dfs: List[pd.DataFrame]) -> pd.DataFrame:
        """Outer join sobre (Anio, SemanaEstadistica) — réplica celda 46."""
        dfs_validos = [d for d in dfs if d is not None and not d.empty]
        if not dfs_validos:
            raise RuntimeError("SINCA: todas las fuentes fallaron. Revisar API/conectividad.")
        if len(dfs_validos) == 1:
            return dfs_validos[0]
        return reduce(
            lambda l, r: pd.merge(l, r, on=['Anio', 'SemanaEstadistica'], how='outer'),
            dfs_validos
        )

    # ------------------------------------------------------------------
    # Reporte de faltantes (missing_strategy=report)
    # ------------------------------------------------------------------
    def _report_missing(self, df_env: pd.DataFrame) -> None:
        """Reporta semanas y fuentes faltantes. No imputa."""
        if self.missing_strategy != 'report':
            return

        n_semanas = len(df_env)
        cols_env = [c for c in df_env.columns if c not in ('Anio', 'SemanaEstadistica')]

        log.info("SINCA: reporte de faltantes (estrategia=report, no imputa):")
        log.info("  Total semanas en df_env_final: %d", n_semanas)
        for col in cols_env:
            n_nan = int(df_env[col].isna().sum())
            pct = 100 * n_nan / max(n_semanas, 1)
            flag = " ⚠" if pct > 10 else ""
            log.info("  %-30s NaN=%4d (%5.1f%%)%s", col, n_nan, pct, flag)

        if self.missing_report:
            log.info("  Fuentes con fallos de descarga/procesamiento:")
            for m in self.missing_report:
                log.info("    - %s (%s): %s", m['fuente'], m['param'], m['motivo'])

    # ------------------------------------------------------------------
    # Run completo
    # ------------------------------------------------------------------
    def run(self) -> Tuple[pd.DataFrame, List[Dict]]:
        """
        Descarga y procesa las 7 fuentes SINCA (3 contaminantes + 4 meteorológicas).
        Devuelve (df_env_final, missing_report).
        """
        specs = []
        for c in self.cfg.sinca.contaminantes:
            c = dict(c); c.setdefault('es_contaminante', True)
            specs.append(c)
        for m in self.cfg.sinca.meteorologicas:
            specs.append(dict(m))

        log.info("SINCA: procesando %d fuentes (estación %d)...", len(specs), self.station_id)
        dfs = [self._process_one(s) for s in specs]

        df_env_final = self._merge_outer(dfs)
        df_env_final = df_env_final.sort_values(
            ['Anio', 'SemanaEstadistica']
        ).reset_index(drop=True)

        self._report_missing(df_env_final)
        log.info("SINCA: df_env_final shape=%s, cols=%s",
                 df_env_final.shape, list(df_env_final.columns))
        return df_env_final, self.missing_report
