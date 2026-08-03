"""
Carga y validación de `config.yaml`.

Uso:
    from tools.config import load_config
    cfg = load_config("tools/config.yaml")
    cfg.sinca.station_id  # → 186
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class StudyCfg:
    name: str
    comunas_objetivo: List[str]
    anio_inicio: int
    anio_fin: int
    anio_test_inicio: int
    descartar_anios_mayores_a: int


@dataclass
class DEISCfg:
    url: str
    local_path: Optional[str]
    causas_interes: List[str]
    cause_translation: Dict[str, str]


@dataclass
class SINCACfg:
    mode: str              # 'local_csv' (default) | 'api'
    local_dir: str         # ruta a CSVs descargados manualmente (modo local_csv)
    station_id: int
    missing_strategy: str  # 'report' | 'impute'
    contaminantes: List[Dict[str, Any]]
    meteorologicas: List[Dict[str, Any]]


@dataclass
class OpenMeteoCfg:
    lat: float
    lon: float
    variables_diarias: List[str]
    fallback_threshold: float


@dataclass
class FeaturesCfg:
    lag_orders: List[int]
    dropna: bool


@dataclass
class TrainCfg:
    chronos: Dict[str, Any]
    scaler: Dict[str, Any]
    pca: Dict[str, Any]
    ml_competencia: Dict[str, Any]
    rolling_window_residuo: int


@dataclass
class RetrainCfg:
    policy: str          # 'drift_only' | 'always' | 'never'
    drift_threshold: float
    champion_dir: str
    challenger_dir: str
    report_path: str


@dataclass
class OutputCfg:
    base_dir: str
    subdirs: Dict[str, str]


@dataclass
class LoggingCfg:
    level: str
    file: str


@dataclass
class Config:
    study: StudyCfg
    deis: DEISCfg
    sinca: SINCACfg
    open_meteo: OpenMeteoCfg
    features: FeaturesCfg
    train: TrainCfg
    retrain: RetrainCfg
    output: OutputCfg
    logging: LoggingCfg
    raw: Dict[str, Any]  # yaml crudo para acceso arbitrario

    # Helpers de paths -----------------------------------------------------
    def output_path(self, key: str) -> str:
        """Devuelve la ruta absoluta de un subdirectorio de salida."""
        return os.path.join(self.output.base_dir, self.output.subdirs[key])

    def ensure_output_dirs(self) -> None:
        """Crea todos los subdirectorios de salida (equivalente a celda 42)."""
        os.makedirs(self.output.base_dir, exist_ok=True)
        for k, sub in self.output.subdirs.items():
            os.makedirs(os.path.join(self.output.base_dir, sub), exist_ok=True)


def load_config(path: str = "tools/config.yaml") -> Config:
    """Carga `config.yaml` y devuelve un objeto `Config` tipado."""
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    return Config(
        study=StudyCfg(**raw["study"]),
        deis=DEISCfg(**raw["deis"]),
        sinca=SINCACfg(**raw["sinca"]),
        open_meteo=OpenMeteoCfg(**raw["open_meteo"]),
        features=FeaturesCfg(**raw["features"]),
        train=TrainCfg(
            chronos=raw["train"]["chronos"],
            scaler=raw["train"]["scaler"],
            pca=raw["train"]["pca"],
            ml_competencia=raw["train"]["ml_competencia"],
            rolling_window_residuo=raw["train"]["rolling_window_residuo"],
        ),
        retrain=RetrainCfg(**raw["retrain"]),
        output=OutputCfg(**raw["output"]),
        logging=LoggingCfg(**raw["logging"]),
        raw=raw,
    )
