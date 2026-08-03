"""
tools/champion_challenger.py — Módulo 5: drift detection + reentrenamiento.

Política: `drift_only` (solo reentrenar si el challenger supera al champion
por más del umbral configurado). Para cada target:

1. Carga el champion existente (trío Scaler+PCA+{Campeon}_Hybrid).
2. Entrena un challenger sobre los datos actuales (HzfTrainer.train_one).
3. Calcula MAE_champion y MAE_challenger sobre el set de validación.
4. MAE_relativo = |MAE_champion - MAE_challenger| / MAE_champion.
5. Si MAE_relativo > drift_threshold (0.10): promover challenger.
6. Genera reporte Markdown con fecha, target, MAEs, decisión.

Referencia spec: PIPELINE_SPEC.md §6.3.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd

from .config import Config
from .hzf_trainer import HZFTrainer, HZFInference, safe_filename, target_clean, wmape

log = logging.getLogger(__name__)


class ChampionChallenger:
    """Drift detection + decisión de reentrenamiento."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.policy = cfg.retrain.policy  # 'drift_only' | 'always' | 'never'
        self.threshold = cfg.retrain.drift_threshold
        self.champion_dir = cfg.output_path('modelos_lags')
        self.challenger_dir = os.path.join(
            cfg.output.base_dir, cfg.retrain.challenger_dir
        )
        self.report_path = os.path.join(
            cfg.output.base_dir, cfg.retrain.report_path
        )

    # ------------------------------------------------------------------
    # Evaluar champion existente sobre datos de validación
    # ------------------------------------------------------------------
    def _eval_champion(self,
                       target: str,
                       df_paper: pd.DataFrame,
                       vars_ambientales: List[str],
                       horizon: int,
                       pred_chronos_test: np.ndarray) -> Tuple[float, str]:
        """
        Carga el trío champion y predice sobre las `horizon` semanas de test.

        Devuelve (mae_champion, champion_name).
        """
        inf = HZFInference(self.cfg, models_dir=self.champion_dir)
        try:
            trio = inf.load_trio(target)
        except FileNotFoundError as e:
            log.warning("  Champion no encontrado para %s: %s", target, e)
            return float('nan'), 'none'

        y_test = df_paper[target].values[-horizon:]
        X_test_env = df_paper[vars_ambientales].iloc[-horizon:]

        X_scaled = trio['scaler'].transform(X_test_env)
        X_pca = trio['pca'].transform(X_scaled)
        pred_ml = trio['modelo'].predict(X_pca)
        pred_champion = np.maximum(pred_chronos_test + pred_ml, 0)

        from sklearn.metrics import mean_absolute_error
        mae = float(mean_absolute_error(y_test, pred_champion))
        return mae, trio['champion']

    # ------------------------------------------------------------------
    # Evaluar un challenger (modelo recién entrenado)
    # ------------------------------------------------------------------
    def _eval_challenger(self,
                         target: str,
                         df_paper: pd.DataFrame,
                         vars_ambientales: List[str],
                         horizon: int,
                         pred_chronos_test: np.ndarray,
                         challenger_artifacts: Dict) -> Tuple[float, str]:
        """
        Carga el trío challenger (recién entrenado por HZFTrainer) y predice.
        """
        y_test = df_paper[target].values[-horizon:]
        X_test_env = df_paper[vars_ambientales].iloc[-horizon:]

        trio = {
            'scaler': joblib.load(challenger_artifacts['scaler']),
            'pca':    joblib.load(challenger_artifacts['pca']),
            'modelo': joblib.load(challenger_artifacts['modelo']),
        }
        champion_name = os.path.basename(challenger_artifacts['modelo']).split('_Hybrid_')[0]

        X_scaled = trio['scaler'].transform(X_test_env)
        X_pca = trio['pca'].transform(X_scaled)
        pred_ml = trio['modelo'].predict(X_pca)
        pred_challenger = np.maximum(pred_chronos_test + pred_ml, 0)

        from sklearn.metrics import mean_absolute_error
        mae = float(mean_absolute_error(y_test, pred_challenger))
        return mae, champion_name

    # ------------------------------------------------------------------
    # Promover challenger → champion
    # ------------------------------------------------------------------
    def _promote(self, target: str, challenger_artifacts: Dict) -> None:
        """Reemplaza los .pkl del champion por los del challenger."""
        sf = safe_filename(target)
        for role in ('scaler', 'pca', 'modelo'):
            src = challenger_artifacts[role]
            # Destino: mismo nombre convencional en champion_dir
            if role == 'scaler':
                dst = os.path.join(self.champion_dir, f'Scaler_{sf}.pkl')
            elif role == 'pca':
                dst = os.path.join(self.champion_dir, f'PCA_{sf}.pkl')
            else:
                # modelo: {Campeon}_Hybrid_{sf}.pkl — preserva el nombre del source
                dst = os.path.join(self.champion_dir, os.path.basename(src))
            # Backup del champion anterior
            if os.path.exists(dst):
                backup_dir = os.path.join(self.champion_dir, '.backup')
                os.makedirs(backup_dir, exist_ok=True)
                ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                os.rename(dst, os.path.join(backup_dir, f'{os.path.basename(dst)}.{ts}'))
            os.replace(src, dst)
        log.info("  ✓ Champion promovido para %s", target)

    # ------------------------------------------------------------------
    # Evaluar un target completo
    # ------------------------------------------------------------------
    def evaluate_one(self,
                     df_modelos: pd.DataFrame,
                     target: str,
                     vars_ambientales: List[str],
                     horizon: int,
                     df_paper: pd.DataFrame,
                     trainer: HZFTrainer,
                     pred_chronos_test: Optional[np.ndarray] = None) -> Dict:
        """
        Compara champion vs challenger para un target. Devuelve dict con decisión.
        """
        sf = safe_filename(target)
        tc = target_clean(target)

        # Saltar si todos ceros (igual que en train)
        if (df_paper[target] == 0).all():
            return {'target': tc, 'skipped': True, 'reason': 'all_zeros'}

        # 1. Entrenar challenger (sin guardar plots para no contaminar)
        os.makedirs(self.challenger_dir, exist_ok=True)
        chal_result = trainer.train_one(
            df_paper, target, vars_ambientales, horizon,
            variant='Challenger',
            dir_prod=self.challenger_dir,
            dir_out=None,            # no plots
            save_artifacts=True,
            save_plots=False,
        )
        if chal_result.get('skipped'):
            return {'target': tc, 'skipped': True}

        # 2. Predicciones Chronos (las mismas para champion y challenger)
        if pred_chronos_test is None:
            y_train = df_paper[target].values[:-horizon]
            y_test = df_paper[target].values[-horizon:]
            pred_chronos_test = trainer.chronos_rolling(y_train, y_test, horizon)

        # 3. MAE champion
        mae_champion, champion_name = self._eval_champion(
            target, df_paper, vars_ambientales, horizon, pred_chronos_test
        )

        # 4. MAE challenger
        mae_challenger, challenger_name = self._eval_challenger(
            target, df_paper, vars_ambientales, horizon, pred_chronos_test,
            chal_result['paths']
        )

        # 5. Drift relativo
        if mae_champion > 0 and not np.isnan(mae_champion):
            mae_relativo = abs(mae_champion - mae_challenger) / mae_champion
        else:
            mae_relativo = float('inf') if not np.isnan(mae_challenger) else 0.0

        # 6. Decisión según política
        if self.policy == 'never':
            decision = 'keep_champion'
            reason = f'policy=never'
        elif self.policy == 'always':
            decision = 'promote_challenger'
            reason = f'policy=always'
        elif self.policy == 'drift_only':
            if mae_relativo > self.threshold:
                decision = 'promote_challenger'
                reason = f'drift={mae_relativo:.3f} > {self.threshold}'
            else:
                decision = 'keep_champion'
                reason = f'drift={mae_relativo:.3f} <= {self.threshold}'
        else:
            raise ValueError(f"política desconocida: {self.policy}")

        # 7. Ejecutar decisión
        promoted = False
        if decision == 'promote_challenger':
            self._promote(target, chal_result['paths'])
            promoted = True
        else:
            # Limpiar artifacts del challenger no promovido
            for p in chal_result['paths'].values():
                if os.path.exists(p):
                    os.remove(p)

        log.info("  %s | Champion=%s MAE=%.2f | Challenger=%s MAE=%.2f | drift=%.3f → %s",
                 tc, champion_name, mae_champion,
                 challenger_name, mae_challenger,
                 mae_relativo, decision)

        return {
            'target': tc,
            'safe_filename': sf,
            'champion_name': champion_name,
            'challenger_name': challenger_name,
            'mae_champion': round(mae_champion, 2),
            'mae_challenger': round(mae_challenger, 2),
            'mae_relativo': round(mae_relativo, 4),
            'threshold': self.threshold,
            'decision': decision,
            'reason': reason,
            'promoted': promoted,
            'timestamp': datetime.now().isoformat(timespec='seconds'),
        }

    # ------------------------------------------------------------------
    # Evaluar todos los targets
    # ------------------------------------------------------------------
    def evaluate_all(self, df_modelos: pd.DataFrame) -> Tuple[pd.DataFrame, str]:
        """
        Compara champion vs challenger para los 13 targets.
        Devuelve (df_reporte, markdown_path).
        """
        from .hzf_trainer import HZFTrainer
        trainer = HZFTrainer(self.cfg)
        df_paper, cols_epi, vars_amb, horizon = trainer._prepare_data(df_modelos, usar_lags=True)

        resultados = []
        for target in cols_epi:
            log.info("Eval %s ...", target)
            r = self.evaluate_one(
                df_modelos, target, vars_amb, horizon, df_paper, trainer
            )
            resultados.append(r)

        df_reporte = pd.DataFrame([
            {k: v for k, v in r.items() if k != 'safe_filename'}
            for r in resultados if not r.get('skipped')
        ])

        md_path = self._write_markdown_report(df_reporte)
        csv_path = md_path.replace('.md', '.csv')
        df_reporte.to_csv(csv_path, index=False)
        log.info("Champion/Challenger: reporte → %s", md_path)
        return df_reporte, md_path

    # ------------------------------------------------------------------
    # Reporte Markdown
    # ------------------------------------------------------------------
    def _write_markdown_report(self, df: pd.DataFrame) -> str:
        """Genera el reporte Markdown con la tabla de decisiones."""
        os.makedirs(os.path.dirname(self.report_path), exist_ok=True)

        promoted = int(df['promoted'].sum()) if 'promoted' in df.columns else 0
        kept = len(df) - promoted

        lines = [
            f"# Champion / Challenger Report",
            f"",
            f"- **Fecha**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **Política**: `{self.policy}`",
            f"- **Umbral drift**: {self.threshold}",
            f"- **Champion dir**: `{self.champion_dir}`",
            f"- **Challenger dir**: `{self.challenger_dir}`",
            f"",
            f"## Resumen",
            f"",
            f"- Targets evaluados: **{len(df)}**",
            f"- Champions promovidos: **{promoted}**",
            f"- Champions conservados: **{kept}**",
            f"",
            f"## Detalle por target",
            f"",
            f"| Target | Champion | MAE Champion | Challenger | MAE Challenger | Drift rel. | Decisión |",
            f"|---|---|---|---|---|---|---|",
        ]
        for _, row in df.iterrows():
            lines.append(
                f"| {row['target']} | {row['champion_name']} | {row['mae_champion']:.2f} "
                f"| {row['challenger_name']} | {row['mae_challenger']:.2f} "
                f"| {row['mae_relativo']:.4f} | "
                f"{'🔄 promote' if row['promoted'] else '✓ keep'} |"
            )

        lines += [
            f"",
            f"## Criterio",
            f"",
            f"```",
            f"MAE_relativo = |MAE_champion - MAE_challenger| / MAE_champion",
            f"if MAE_relativo > {self.threshold}: promote challenger",
            f"else: keep champion",
            f"```",
            f"",
            f"## Backups",
            f"",
            f"Los champions reemplazados se respaldan en "
            f"`{self.champion_dir}/.backup/` con timestamp.",
            f"",
        ]

        with open(self.report_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        return self.report_path
