"""
tools/cli.py — CLI dispatcher para el pipeline RespiratorIA 2.

Uso:
    python -m tools <command> [--config CONFIG] [options]

Comandos:
    deis-fetch        Descarga + procesa DEIS. Exporta Backend_Data/.
    sinca-fetch       Descarga + procesa SINCA (station 186).
    build-features    Merge salud+ambiente + lags. Devuelve df_modelos.
    train             Entrena 13 targets (variant lags/nolags).
    retrain           Champion-challenger con drift policy.
    inference         Predicción puntual para un target.
    full              Pipeline completo: deis → sinca → features → train.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import List, Optional

from .config import Config, load_config


def _setup_logging(cfg: Config) -> None:
    """Configura logging a stdout + archivo."""
    os.makedirs(os.path.dirname(cfg.logging.file) or '.', exist_ok=True)
    fmt = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    logging.basicConfig(
        level=getattr(logging, cfg.logging.level.upper()),
        format=fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(cfg.logging.file, encoding='utf-8'),
        ],
    )


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------

def cmd_deis_fetch(cfg: Config, args) -> None:
    from .deis import DEISFetcher
    fetcher = DEISFetcher(cfg)
    df_backend, df_aglomerado, path = fetcher.run()
    print(f"\n✓ DEIS: {len(df_backend)} filas backend, {len(df_aglomerado)} semanas aglomerado.")
    print(f"  CSV: {path}")


def cmd_sinca_fetch(cfg: Config, args) -> None:
    from .sinca import SINCAFetcher
    fetcher = SINCAFetcher(cfg)
    df_env, missing = fetcher.run()
    print(f"\n✓ SINCA: df_env_final shape={df_env.shape}")
    print(f"  Fuentes con problemas: {len(missing)}")
    # Guardar para build-features
    out = os.path.join(cfg.output.base_dir, '.cache', 'df_env_final.parquet')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    df_env.to_parquet(out, index=False)
    print(f"  Cache: {out}")


def cmd_build_features(cfg: Config, args) -> None:
    from .features import build_features
    from .deis import DEISFetcher
    from .sinca import SINCAFetcher

    # Cargar DEIS
    deis = DEISFetcher(cfg)
    df_salud = deis.fetch_parquet()
    _, df_aglomerado = deis.process(df_salud)

    # Cargar SINCA (cache o fresh)
    cache = os.path.join(cfg.output.base_dir, '.cache', 'df_env_final.parquet')
    if os.path.exists(cache) and not args.refresh_sinca:
        import pandas as pd
        df_env = pd.read_parquet(cache)
        print(f"  SINCA: desde cache {cache}")
    else:
        sinca = SINCAFetcher(cfg)
        df_env, _ = sinca.run()

    df_modelos = build_features(df_aglomerado, df_env, cfg)
    out = os.path.join(cfg.output_path('backend_data'),
                       f'Dataset_Modelos_{cfg.study.name}.csv')
    df_modelos.to_csv(out, index=False)
    print(f"\n✓ Features: df_modelos shape={df_modelos.shape} → {out}")


def cmd_train(cfg: Config, args) -> None:
    import pandas as pd
    from .hzf_trainer import HZFTrainer

    # Cargar df_modelos
    path = os.path.join(cfg.output_path('backend_data'),
                        f'Dataset_Modelos_{cfg.study.name}.csv')
    if not os.path.exists(path):
        print(f"✗ No existe {path}. Ejecuta `build-features` primero.")
        sys.exit(1)
    df_modelos = pd.read_csv(path)
    print(f"  Cargado: {path} shape={df_modelos.shape}")

    trainer = HZFTrainer(cfg)
    df_res, csv_path = trainer.train_all(
        df_modelos,
        variant=args.variant,
        save_artifacts=not args.no_save,
        save_plots=not args.no_plots,
    )
    print(f"\n✓ Train ({args.variant}): {len(df_res)} targets entrenados.")
    print(df_res.to_string(index=False))
    print(f"\n  Métricas: {csv_path}")


def cmd_retrain(cfg: Config, args) -> None:
    import pandas as pd
    from .champion_challenger import ChampionChallenger

    path = os.path.join(cfg.output_path('backend_data'),
                        f'Dataset_Modelos_{cfg.study.name}.csv')
    if not os.path.exists(path):
        print(f"✗ No existe {path}. Ejecuta `build-features` primero.")
        sys.exit(1)
    df_modelos = pd.read_csv(path)

    cc = ChampionChallenger(cfg)
    df_reporte, md_path = cc.evaluate_all(df_modelos)
    print(f"\n✓ Retrain (policy={cfg.retrain.policy}):")
    print(df_reporte.to_string(index=False))
    print(f"\n  Reporte: {md_path}")


def cmd_inference(cfg: Config, args) -> None:
    import numpy as np
    import pandas as pd
    from .hzf_trainer import HZFInference

    inf = HZFInference(cfg, models_dir=args.models_dir or cfg.output_path('modelos_lags'))

    # Cargar histórico del target (últimas N semanas)
    df = pd.read_csv(args.history_csv)
    y_history = df[args.target].values
    # Variables ambientales para el horizonte
    X_env = df[args.env_cols.split(',')].values[-args.horizon:] \
        if args.env_cols else None
    if X_env is None:
        print("✗ --env-cols requerido para inference.")
        sys.exit(1)

    result = inf.predict(args.target, y_history, X_env, args.horizon)
    print(f"\n✓ Inference {args.target} (horizon={args.horizon}):")
    print(f"  Champion: {result['champion']}")
    print(f"  Chronos:  {result['chronos']}")
    print(f"  ML corr:  {result['ml_correction']}")
    print(f"  Hybrid:   {result['hybrid']}")


def cmd_full(cfg: Config, args) -> None:
    """Pipeline completo: deis → sinca → features → train."""
    print("=== 1/4: DEIS ===")
    cmd_deis_fetch(cfg, args)
    print("\n=== 2/4: SINCA ===")
    cmd_sinca_fetch(cfg, args)
    print("\n=== 3/4: Features ===")
    cmd_build_features(cfg, args)
    print("\n=== 4/4: Train ===")
    cmd_train(cfg, args)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog='tools',
        description='RespiratorIA 2 — pipeline anual HZF Hybrid + Lags',
    )
    parser.add_argument('command', choices=[
        'deis-fetch', 'sinca-fetch', 'build-features', 'train',
        'retrain', 'inference', 'full',
    ])
    parser.add_argument('--config', default='tools/config.yaml',
                        help='Path a config.yaml (default: tools/config.yaml)')
    parser.add_argument('--variant', default='lags', choices=['lags', 'nolags'],
                        help='Variante de entrenamiento (default: lags)')
    parser.add_argument('--refresh-sinca', action='store_true',
                        help='Forzar re-descarga SINCA (ignora cache)')
    parser.add_argument('--no-save', action='store_true',
                        help='No guardar artifacts .pkl (solo métricas)')
    parser.add_argument('--no-plots', action='store_true',
                        help='No guardar PNGs de forecast/features')
    # inference-only
    parser.add_argument('--models-dir', help='Dir de modelos para inference')
    parser.add_argument('--target', help='Target para inference')
    parser.add_argument('--history-csv', help='CSV con histórico para inference')
    parser.add_argument('--env-cols', help='Columnas ambientales (comma-sep) para inference')
    parser.add_argument('--horizon', type=int, default=4, help='Horizon (semanas)')

    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    _setup_logging(cfg)
    cfg.ensure_output_dirs()

    dispatch = {
        'deis-fetch':      cmd_deis_fetch,
        'sinca-fetch':     cmd_sinca_fetch,
        'build-features':  cmd_build_features,
        'train':           cmd_train,
        'retrain':         cmd_retrain,
        'inference':       cmd_inference,
        'full':            cmd_full,
    }
    dispatch[args.command](cfg, args)
    return 0


if __name__ == '__main__':
    sys.exit(main())
