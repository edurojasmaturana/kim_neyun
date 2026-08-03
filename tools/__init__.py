"""

API pública:
    from tools import (
        load_config,
        DEISFetcher,
        SINCAFetcher,
        OpenMeteoFetcher,
        build_features,
        HZFTrainer,
        HZFInference,
        ChampionChallenger,
        safe_filename,
        target_clean,
        wmape,
    )
"""

from .config import load_config           # noqa: F401

# Los módulos siguientes se importan lazy para no romper `import tools`
# cuando alguna dependencia pesada (torch, chronos) no está instalada.

__all__ = [
    "load_config",
    "DEISFetcher",
    "SINCAFetcher",
    "OpenMeteoFetcher",
    "build_features",
    "HZFTrainer",
    "HZFInference",
    "ChampionChallenger",
    "safe_filename",
    "target_clean",
    "wmape",
]


def __getattr__(name):
    """Lazy imports para evitar cargar torch/chronos al hacer `import tools`."""
    if name == "DEISFetcher":
        from .deis import DEISFetcher
        return DEISFetcher
    if name == "SINCAFetcher":
        from .sinca import SINCAFetcher
        return SINCAFetcher
    if name == "OpenMeteoFetcher":
        from .open_meteo import OpenMeteoFetcher
        return OpenMeteoFetcher
    if name == "build_features":
        from .features import build_features
        return build_features
    if name == "HZFTrainer":
        from .hzf_trainer import HZFTrainer
        return HZFTrainer
    if name == "HZFInference":
        from .hzf_trainer import HZFInference
        return HZFInference
    if name == "ChampionChallenger":
        from .champion_challenger import ChampionChallenger
        return ChampionChallenger
    if name == "safe_filename":
        from .hzf_trainer import safe_filename
        return safe_filename
    if name == "target_clean":
        from .hzf_trainer import target_clean
        return target_clean
    if name == "wmape":
        from .hzf_trainer import wmape
        return wmape
    raise AttributeError(f"module 'tools' has no attribute {name!r}")


__version__ = "0.1.0"
