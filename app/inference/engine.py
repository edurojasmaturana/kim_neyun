"""Motor híbrido HZF: Chronos-T5 (trayectoria base) + ML (corrección de residuos).

Es el corazón del PoC (`poc/api_motor (poc).py`) refactorizado a una clase que
carga el modelo una vez y expone los cálculos táctico (1 semana) y macro
(52 semanas). Ya no responde requests: el job batch persiste los resultados.
"""

import glob
import logging
import os
import warnings

import joblib
import numpy as np
import pandas as pd
import sklearn
import torch
from chronos import ChronosPipeline
from epiweeks import Week
from sklearn.exceptions import InconsistentVersionWarning

from shared import config
from shared.catalog import TARGETS_LAGS, TARGETS_NOLAGS, TODOS_TARGETS

logger = logging.getLogger(__name__)


def _verificar_versiones_artefactos() -> None:
    """Aborta si sklearn/numpy no coinciden con las usadas al serializar los .pkl.

    Cargar un Scaler/PCA con otra versión puede (1) fallar el import de la clase o,
    peor, (2) cargar bien y PREDECIR DISTINTO en silencio — inaceptable en un motor
    clínico. Fallamos al arrancar el batch, no en producción.
    Override de emergencia: KIM_SKIP_VERSION_GUARD=1.
    """
    esperadas = {
        "scikit-learn": config.ARTIFACT_SKLEARN_VERSION,
        "numpy": config.ARTIFACT_NUMPY_VERSION,
    }
    actuales = {"scikit-learn": sklearn.__version__, "numpy": np.__version__}
    desajustes = {
        k: (esperadas[k], actuales[k]) for k in esperadas if actuales[k] != esperadas[k]
    }
    if not desajustes:
        return
    detalle = ", ".join(
        f"{k}: esperado {esp} / instalado {act}" for k, (esp, act) in desajustes.items()
    )
    msg = (
        f"Versiones distintas a las usadas al entrenar los .pkl ({detalle}); "
        "riesgo de predicciones inconsistentes."
    )
    if config.SKIP_VERSION_GUARD:
        logger.warning("[VERSION GUARD OMITIDO] %s", msg)
    else:
        raise RuntimeError(
            f"{msg} Alinea inference/requirements.txt o define "
            "KIM_SKIP_VERSION_GUARD=1 para forzar (bajo tu responsabilidad)."
        )


class MotorHibrido:
    """Carga Chronos + artefactos ML (.pkl/scaler/PCA) y ejecuta las inferencias."""

    def __init__(self):
        _verificar_versiones_artefactos()
        # Que un desajuste de versión detectado por joblib al deserializar también
        # sea fatal, no un warning perdido en los logs.
        if not config.SKIP_VERSION_GUARD:
            warnings.filterwarnings("error", category=InconsistentVersionWarning)

        logger.info("Cargando Chronos: %s", config.CHRONOS_MODEL)
        self.pipeline_chronos = ChronosPipeline.from_pretrained(
            config.CHRONOS_MODEL, device_map="cpu", torch_dtype=torch.bfloat16
        )
        self.modelos_ml: dict = {}
        self.scalers: dict = {}
        self.pcas: dict = {}
        logger.info("Cargando pesos de Machine Learning desde %s", config.MODELS_DIR)
        self._cargar_artefactos(TARGETS_LAGS, os.path.join(config.MODELS_DIR, "Modelos_Lags"))
        self._cargar_artefactos(TARGETS_NOLAGS, os.path.join(config.MODELS_DIR, "Modelos_NoLags"))

    @staticmethod
    def _nombre_archivo(target: str) -> str:
        """Sanitiza el nombre del target a la convención de los .pkl entrenados.

        Las columnas del CSV (y por tanto las claves de target) usan `/` y `()`
        —p.ej. `Cause_Acute_Bronchitis/Bronchiolitis`, `Cause_COVID-19_(Confirmed)`—
        pero el pipeline de laboratorio guardó los archivos sanitizados:
        `..._Bronchitis_Bronchiolitis.pkl`, `..._COVID-19_Confirmed.pkl`.
        """
        return target.replace("/", "_").replace("(", "").replace(")", "")

    def _cargar_artefactos(self, targets, carpeta):
        for t in targets:
            if not (t.startswith("Num") or t.startswith("Cause")):
                continue
            tf = self._nombre_archivo(t)
            matches = glob.glob(f"{carpeta}/*_Hybrid_{tf}.pkl")
            if not matches:
                # Ausencia legítima de artefactos: degrada a Zero-Shot (como el PoC).
                logger.warning(
                    "Artefactos faltantes para %s en %s. Operará en modo Zero-Shot.",
                    t, carpeta,
                )
                continue
            # Si los archivos EXISTEN pero fallan al cargar (versión incompatible,
            # .pkl corrupto o puntero LFS sin resolver), NO degradamos en silencio:
            # es un error operativo que debe romper el batch. Salvo override explícito.
            try:
                self.modelos_ml[t] = joblib.load(matches[0])
                self.scalers[t] = joblib.load(f"{carpeta}/Scaler_{tf}.pkl")
                self.pcas[t] = joblib.load(f"{carpeta}/PCA_{tf}.pkl")
            except Exception as e:  # noqa: BLE001
                if config.SKIP_VERSION_GUARD:
                    logger.warning(
                        "[GUARD OMITIDO] Error cargando artefactos de %s (%s); cae a Zero-Shot.",
                        t, e,
                    )
                    self.modelos_ml.pop(t, None)
                    self.scalers.pop(t, None)
                    self.pcas.pop(t, None)
                else:
                    raise RuntimeError(
                        f"Error cargando artefactos de {t} en {carpeta}: {e}. "
                        "Los archivos existen pero no se pudieron deserializar "
                        "(¿versión incompatible, .pkl corrupto o puntero LFS sin resolver?)."
                    ) from e

    # --- TÁCTICO: 1 semana híbrida ---
    def predecir_semana(self, df_historia, hospital_input, fecha_ref, clima):
        df_env_completo = pd.DataFrame([clima or {}]).fillna(0.0)
        df_hosp = df_historia[
            df_historia["EstablecimientoGlosa"] == hospital_input
        ].sort_values(["Anio", "SemanaEstadistica"])

        semana_epi = Week.fromdate(fecha_ref, system="cdc")
        year_ref = semana_epi.year
        week_ref = semana_epi.week
        df_hosp = df_hosp[
            (df_hosp["Anio"] < year_ref)
            | ((df_hosp["Anio"] == year_ref) & (df_hosp["SemanaEstadistica"] < week_ref))
        ]
        if df_hosp.empty:
            return None

        res = {"Causas": {}, "Edades": {}, "Total": 0}
        for t in TODOS_TARGETS:
            if t not in df_hosp.columns and f"Cause_{t}" not in df_hosp.columns:
                continue
            series = torch.tensor(df_hosp[t].values[-104:].astype(np.float32))
            forecast = self.pipeline_chronos.predict(series, 1, num_samples=50)
            pred_base = np.quantile(forecast[0].numpy(), 0.5, axis=0)[0]

            ajuste = 0
            if t in self.modelos_ml:
                try:
                    cols_requeridas = self.scalers[t].feature_names_in_
                    for col in cols_requeridas:
                        if col not in df_env_completo.columns:
                            df_env_completo[col] = 0.0
                    df_env_filtrado = df_env_completo[cols_requeridas].fillna(0.0)
                    env_pca = self.pcas[t].transform(self.scalers[t].transform(df_env_filtrado))
                    ajuste = self.modelos_ml[t].predict(env_pca)[0]
                except Exception:  # noqa: BLE001
                    pass

            val = max(0, int(round(pred_base + ajuste)))
            if t.startswith("Cause_"):
                res["Causas"][t.replace("Cause_", "")] = val
            elif t.startswith("Num"):
                res["Edades"][t.replace("Num", "")] = val

        # BOTTOM-UP FORECASTING (idéntico al PoC)
        total_causas = sum(res["Causas"].values())
        res["Total"] = total_causas
        suma_edades_cruda = sum(res["Edades"].values())
        if suma_edades_cruda > 0 and total_causas > 0:
            for edad_key, valor_crudo in res["Edades"].items():
                proporcion = valor_crudo / suma_edades_cruda
                res["Edades"][edad_key] = int(round(proporcion * total_causas))
            diferencia = total_causas - sum(res["Edades"].values())
            if diferencia != 0:
                clave_mayor = max(res["Edades"], key=res["Edades"].get)
                res["Edades"][clave_mayor] += diferencia

        return {
            "hospital": hospital_input,
            "semana_epi": week_ref,
            "año": year_ref,
            "estimaciones": res,
            "temperatura_referencia": (clima or {}).get("Temperatura_Avg", 0),
        }

    # --- ESTRATÉGICO: 52 semanas macro ---
    def proyeccion_anual(self, df_historia, hospital_input, anio_objetivo):
        df_hosp = df_historia[
            df_historia["EstablecimientoGlosa"] == hospital_input
        ].sort_values(["Anio", "SemanaEstadistica"])
        df_contexto = df_hosp[df_hosp["Anio"] < anio_objetivo]
        if df_contexto.empty:
            return None

        df_real = df_hosp[df_hosp["Anio"] == anio_objetivo]
        causas_cols = [c for c in TODOS_TARGETS if c.startswith("Cause_")]
        predicciones_causas = []
        for t in causas_cols:
            if t not in df_contexto.columns:
                continue
            series = torch.tensor(df_contexto[t].values[-104:].astype(np.float32))
            forecast = self.pipeline_chronos.predict(series, 52, num_samples=20)
            pred_mediana = np.quantile(forecast[0].numpy(), 0.5, axis=0)
            predicciones_causas.append(np.maximum(0, pred_mediana))

        total_proyectado = np.sum(predicciones_causas, axis=0)
        semanas_totales = list(range(1, 53))
        curva_real = []
        if not df_real.empty:
            for sem in semanas_totales:
                row = df_real[df_real["SemanaEstadistica"] == sem]
                if not row.empty:
                    suma_real = int(
                        row[[c for c in causas_cols if c in row.columns]].sum(axis=1).values[0]
                    )
                    curva_real.append(suma_real)
                else:
                    curva_real.append(None)
        else:
            curva_real = [None] * 52

        return {
            "hospital": hospital_input,
            "anio": anio_objetivo,
            "semanas": semanas_totales,
            "curva_ia": [int(x) for x in total_proyectado],
            "curva_real": curva_real,
        }
