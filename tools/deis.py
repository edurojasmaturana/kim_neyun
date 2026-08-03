"""
tools/deis.py — Módulo 1: descarga y limpieza DEIS (salud).

Reproduce celda 44 del notebook RespiratorIA2.ipynb:
- Lectura del parquet DEIS (URL datos.gob.cl o path local).
- Filtro por comunas (Temuco, Padre Las Casas).
- Filtro por 8 causas exactas (literal DEIS).
- Traducción al inglés via cause_translation.
- Construcción de df_backend (nivel hospital) y df_aglomerado (nivel ciudad).
- Export CSV a Backend_Data/.

Referencia spec: PIPELINE_SPEC.md §2.
"""
from __future__ import annotations

import logging
import os
from typing import Tuple

import pandas as pd
import requests

from .config import Config

log = logging.getLogger(__name__)


# Columnas obligatorias del backend (literal notebook celda 44, §2.5)
COLUMNAS_BACKEND = [
    'Anio', 'SemanaEstadistica', 'EstablecimientoGlosa', 'Total_Consultations',
    'NumMenor1Anio', 'Num1a4Anios', 'Num5a14Anios', 'Num15a64Anios', 'Num65oMas',
    'Cause_Acute_Bronchitis/Bronchiolitis', 'Cause_Bronchial_Obstructive_Crisis',
    'Cause_COVID-19_(Confirmed)', 'Cause_COVID-19_(Suspected)', 'Cause_Influenza',
    'Cause_Other_Respiratory_Causes', 'Cause_Pneumonia', 'Cause_Upper_Respiratory_Infection'
]


class DEISFetcher:
    """Descarga y procesa el dataset DEIS de urgencias respiratorias semanales."""

    def __init__(self, cfg: Config):
        self.cfg = cfg

    # ------------------------------------------------------------------
    # Descarga (parquet)
    # ------------------------------------------------------------------
    def fetch_parquet(self) -> pd.DataFrame:
        """Carga el parquet DEIS: si existe path local lo usa, si no descarga de URL.

        La descarga usa reintentos automáticos con reanudación (HTTP Range),
        porque datos.gob.cl a veces corta la conexión a mitad de archivo.
        """
        local = self.cfg.deis.local_path
        if local and os.path.exists(local):
            # Verificar que el archivo no esté vacío o truncado
            if os.path.getsize(local) > 1_000_000:  # > 1 MB, integrity check básico
                log.info("DEIS: cargando desde path local %s", local)
                return pd.read_parquet(local)
            else:
                log.warning("DEIS: path local %s existe pero pesa <1MB, re-descargando.", local)

        url = self.cfg.deis.url
        log.info("DEIS: descargando parquet desde %s", url)
        cache_dir = os.path.join(self.cfg.output.base_dir, ".cache")
        os.makedirs(cache_dir, exist_ok=True)
        tmp = os.path.join(cache_dir, "deis.parquet")

        # Descarga con reintentos y reanudación HTTP Range
        max_retries = 5
        for intento in range(1, max_retries + 1):
            try:
                self._download_with_resume(url, tmp)
                df = pd.read_parquet(tmp)
                log.info("DEIS: parquet cargado. Shape=%s (intento %d/%d)",
                         df.shape, intento, max_retries)
                # Mover al path local permanente si está configurado
                if local:
                    os.makedirs(os.path.dirname(local) or '.', exist_ok=True)
                    os.replace(tmp, local)
                    log.info("DEIS: parquet guardado en %s", local)
                return df
            except Exception as e:
                log.warning("DEIS: intento %d/%d fallido: %s", intento, max_retries, e)
                if intento == max_retries:
                    raise RuntimeError(
                        f"DEIS: no se pudo descargar el parquet tras {max_retries} intentos. "
                        f"Último error: {e}. Sugerencia: descargar manualmente con "
                        f"'wget -c -O {local or 'deis.parquet'} {url}' y volver a correr."
                    ) from e
                # Backoff exponencial: 2, 4, 8, 16 segundos
                import time
                wait = 2 ** intento
                log.info("DEIS: esperando %ds antes de reintentar...", wait)
                time.sleep(wait)

    def _download_with_resume(self, url: str, dest: str) -> None:
        """Descarga con soporte HTTP Range para reanudar descargas interrumpidas."""
        # Tamaño ya descargado (si existe archivo parcial)
        offset = 0
        if os.path.exists(dest):
            offset = os.path.getsize(dest)
            log.info("DEIS: reanudando desde byte %d (%.1f MB ya descargados)",
                     offset, offset / 1e6)

        headers = {"User-Agent": "RespiratorIA2/1.0"}
        if offset > 0:
            headers["Range"] = f"bytes={offset}-"

        r = requests.get(url, timeout=180, stream=True, headers=headers)
        # Si el servidor no soporta Range (status 200 en vez de 206), empezar de 0
        if offset > 0 and r.status_code == 200:
            log.info("DEIS: servidor no soporta Range, descargando desde cero.")
            offset = 0
            mode = "wb"
        elif r.status_code == 206:
            mode = "ab"
        else:
            r.raise_for_status()
            mode = "wb"

        r.raise_for_status()
        with open(dest, mode) as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                if chunk:
                    f.write(chunk)

    # ------------------------------------------------------------------
    # Procesamiento (celda 44 del notebook)
    # ------------------------------------------------------------------
    def process(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Aplica el pipeline del notebook y devuelve (df_backend, df_aglomerado).

        - df_backend:    nivel hospital, 17 columnas.
        - df_aglomerado: nivel ciudad (suma de hospitales por semana).
        """
        comunas = self.cfg.study.comunas_objetivo
        causas = self.cfg.deis.causas_interes
        translation = self.cfg.deis.cause_translation

        # 1. Filtro comunas (celda 44 §1)
        df_filtrado = df[df['ComunaGlosa'].isin(comunas)].copy()
        log.info("DEIS: tras filtro comunas %s → %d filas", comunas, len(df_filtrado))

        # 2. Filtro causas + traducción (celda 44 §2)
        df_filtrado = df_filtrado[df_filtrado['Causa'].isin(causas)].copy()
        df_filtrado['Causa_Eng'] = df_filtrado['Causa'].map(translation)
        log.info("DEIS: tras filtro causas → %d filas", len(df_filtrado))

        # 3. Agrupación por hospital (edades + total) — celda 44 §3
        hosp_ages = df_filtrado.groupby(
            ['Anio', 'SemanaEstadistica', 'EstablecimientoGlosa']
        ).agg({
            'NumTotal': 'sum', 'NumMenor1Anio': 'sum', 'Num1a4Anios': 'sum',
            'Num5a14Anios': 'sum', 'Num15a64Anios': 'sum', 'Num65oMas': 'sum'
        }).reset_index().rename(columns={'NumTotal': 'Total_Consultations'})

        # 4. Causas específicas (pivot) — celda 44 §3
        hosp_weekly = (
            df_filtrado
            .groupby(['Anio', 'SemanaEstadistica', 'EstablecimientoGlosa', 'Causa_Eng'])['NumTotal']
            .sum().unstack().fillna(0)
        )
        hosp_weekly.columns = [f"Cause_{col.replace(' ', '_')}" for col in hosp_weekly.columns]
        hosp_weekly = hosp_weekly.reset_index()

        # 5. Merge edades + causas — celda 44 §3
        df_backend = pd.merge(
            hosp_ages, hosp_weekly,
            on=['Anio', 'SemanaEstadistica', 'EstablecimientoGlosa']
        )
        df_backend = df_backend.sort_values(
            ['EstablecimientoGlosa', 'Anio', 'SemanaEstadistica']
        ).reset_index(drop=True)

        # 6. Asegurar columnas obligatorias (celda 44 §4) — rellena con 0 si faltan
        for col in COLUMNAS_BACKEND:
            if col not in df_backend.columns:
                df_backend[col] = 0
        df_backend = df_backend[COLUMNAS_BACKEND]

        # 7. Aglomerado nivel ciudad (celda 46 §aglomerado) — suma hospitales por semana
        df_aglomerado = df_backend.groupby(
            ['Anio', 'SemanaEstadistica']
        ).sum(numeric_only=True).reset_index()

        log.info("DEIS: df_backend shape=%s, df_aglomerado shape=%s",
                 df_backend.shape, df_aglomerado.shape)
        return df_backend, df_aglomerado

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    def export_backend(self, df_backend: pd.DataFrame) -> str:
        """Exporta df_backend a Backend_Data/API_Epidemiologia_{study}.csv."""
        out_dir = self.cfg.output_path('backend_data')
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"API_Epidemiologia_{self.cfg.study.name}.csv")
        df_backend.to_csv(path, index=False)
        log.info("DEIS: backend exportado a %s", path)
        return path

    # ------------------------------------------------------------------
    # Run completo
    # ------------------------------------------------------------------
    def run(self) -> Tuple[pd.DataFrame, pd.DataFrame, str]:
        """Pipeline completo: fetch → process → export. Devuelve (backend, aglomerado, csv_path)."""
        df = self.fetch_parquet()
        df_backend, df_aglomerado = self.process(df)
        path = self.export_backend(df_backend)
        return df_backend, df_aglomerado, path
