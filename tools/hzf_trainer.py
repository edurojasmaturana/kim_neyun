"""
tools/hzf_trainer.py — Módulo 4: entrenamiento Chronos T5 Hybrid.

Reproduce celda 49 del notebook RespiratorIA2.ipynb:
- Para cada target en cols_epidemiologicas (13 targets):
    * Saltar si todos ceros (caso COVID-19 Suspected).
    * Split temporal: train = 2021-2023, test = 2024-2025.
    * Chronos rolling forecast (step_size=4, num_samples=50, quantile=0.5).
    * residuo_train = y_train - rolling(4).mean().
    * StandardScaler fit en train, transform en test.
    * PCA(n_components=0.90, random_state=42) fit en train, transform en test.
    * GridSearchCV(cv=3, scoring='neg_MAE') para Ridge/RandomForest/XGBoost.
    * Campeón = min MAE.
    * pred_hibrida = max(0, chronos + champion.predict(X_test_pca)).
    * WMAPE para Chronos y para Híbrido.
    * Exporta 3 .pkl: Scaler_{t}.pkl, PCA_{t}.pkl, {Campeon}_Hybrid_{t}.pkl.
    * Plots: Forecast + Feature Importance.

Referencia spec: PIPELINE_SPEC.md §5.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd

from .config import Config

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers (literales del notebook)
# ---------------------------------------------------------------------------

def safe_filename(target: str) -> str:
    """Conversión literal del notebook (celda 49, línea 51).

    target → safe_filename
    'Total_Consultations'                 → 'Total_Consultations'
    'Cause_Acute_Bronchitis/Bronchiolitis' → 'Cause_Acute_Bronchitis_Bronchiolitis'
    'Cause_COVID-19_(Confirmed)'          → 'Cause_COVID-19_Confirmed'
    """
    return target.replace('/', '_').replace(' ', '_').replace('(', '').replace(')', '')


def target_clean(target: str) -> str:
    """Limpieza del nombre para mostrar en logs/títulos (celda 49, línea 50)."""
    return target.replace('_', ' ').replace('Cause ', '')


def wmape(real: np.ndarray, pred: np.ndarray) -> float:
    """WMAPE literal del notebook: sum(|y - pred|) / sum(y) * 100."""
    return float((np.sum(np.abs(real - pred)) / np.sum(real)) * 100)


# ---------------------------------------------------------------------------
# Trainer
# ---------------------------------------------------------------------------

class HZFTrainer:
    """Entrenador Chronos-T5 Hybrid + Lags (réplica 1:1 de celda 49)."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._chronos = None  # lazy load

    # ------------------------------------------------------------------
    # Chronos (lazy)
    # ------------------------------------------------------------------
    def _load_chronos(self):
        """Carga ChronosPipeline bajo demanda (torch es pesado)."""
        if self._chronos is None:
            import torch
            from chronos import ChronosPipeline
            ch = self.cfg.train.chronos
            dtype = getattr(torch, ch['torch_dtype'])  # 'bfloat16' → torch.bfloat16
            log.info("Chronos: cargando %s (dtype=%s, device=%s)",
                     ch['model_name'], ch['torch_dtype'], ch['device_map'])
            self._chronos = ChronosPipeline.from_pretrained(
                ch['model_name'],
                device_map=ch['device_map'],
                torch_dtype=dtype,
            )
        return self._chronos

    # ------------------------------------------------------------------
    # Chronos rolling forecast (celda 49 §A)
    # ------------------------------------------------------------------
    def chronos_rolling(self,
                        y_train: np.ndarray,
                        y_test: np.ndarray,
                        horizon: int) -> np.ndarray:
        """
        Rolling forecast con step_size del config. Devuelve predicciones para
        las `horizon` semanas de test.

        Réplica literal de celda 49 §A:
            step_size = 4
            pred_chronos_list = []
            for i in range(0, horizon, step_size):
                ctx = np.concatenate([y_train, y_test[:i]])
                hz = min(step_size, horizon - i)
                forecast = pipeline.predict(torch.tensor(ctx), prediction_length=hz, num_samples=50)
                pred_chronos_list.extend(np.quantile(forecast[0].numpy(), 0.5, axis=0))
        """
        import torch
        ch = self.cfg.train.chronos
        pipeline = self._load_chronos()

        step_size = ch['step_size']
        num_samples = ch['num_samples']
        quantile = ch['quantile']

        preds = []
        for i in range(0, horizon, step_size):
            ctx = np.concatenate([y_train, y_test[:i]])
            hz = min(step_size, horizon - i)
            forecast = pipeline.predict(
                torch.tensor(ctx),
                prediction_length=hz,
                num_samples=num_samples,
            )
            preds.extend(np.quantile(forecast[0].numpy(), quantile, axis=0))
        return np.array(preds)

    # ------------------------------------------------------------------
    # Split temporal (celda 49 §1)
    # ------------------------------------------------------------------
    def _prepare_data(self, df_modelos: pd.DataFrame,
                      usar_lags: bool = True) -> Tuple[pd.DataFrame, List[str], List[str], int]:
        """
        Prepara df_paper + listas de columnas + horizon.

        Devuelve (df_paper, cols_epidemiologicas, vars_ambientales, horizon).
        """
        df_paper = df_modelos[
            (df_modelos['Anio'] >= self.cfg.study.anio_inicio) &
            (df_modelos['Anio'] <= self.cfg.study.anio_fin)
        ].copy()
        df_paper = df_paper.sort_values(
            ['Anio', 'SemanaEstadistica']
        ).reset_index(drop=True)

        # horizon = semanas de test (2024 + 2025)
        horizon = len(df_paper[df_paper['Anio'] >= self.cfg.study.anio_test_inicio])

        # Columnas epidemiológicas = targets (celda 49 §1)
        cols_epidemiologicas = [
            c for c in df_paper.columns
            if c.startswith('Cause_') or c.startswith('Num') or c == 'Total_Consultations'
        ]
        cols_base = ['Anio', 'SemanaEstadistica'] + cols_epidemiologicas

        # Variables ambientales (celda 49 §1)
        if usar_lags:
            vars_ambientales = [c for c in df_paper.columns if c not in cols_base]
        else:
            vars_ambientales = [c for c in df_paper.columns
                                if c not in cols_base and 'Lag' not in c]

        log.info("HZF: df_paper=%s, horizon=%d, targets=%d, vars_ambientales=%d (lags=%s)",
                 df_paper.shape, horizon, len(cols_epidemiologicas),
                 len(vars_ambientales), usar_lags)
        return df_paper, cols_epidemiologicas, vars_ambientales, horizon

    # ------------------------------------------------------------------
    # ML competition (celda 49 §C)
    # ------------------------------------------------------------------
    def _ml_competition(self, X_train_pca: np.ndarray,
                        residuo_train: np.ndarray) -> Tuple[str, Any, Dict[str, float]]:
        """
        GridSearchCV para Ridge/RandomForest/XGBoost. Devuelve (nombre_campeon,
        modelo_campeon, scores).

        Réplica literal de celda 49 §C. Los constructores de los modelos llevan
        random_state=42 (y XGBoost objective='reg:squarederror'); los grids
        solo contienen los hiperparámetros a buscar.
        """
        from sklearn.linear_model import Ridge
        from sklearn.ensemble import RandomForestRegressor
        from xgboost import XGBRegressor
        from sklearn.model_selection import GridSearchCV

        ml_cfg = self.cfg.train.ml_competencia
        cv = ml_cfg['cv']
        scoring = ml_cfg['scoring']
        n_jobs = ml_cfg['n_jobs']

        # Constructores con args fijos (igual que notebook celda 49 §C)
        modelos_base = {
            'Ridge':        Ridge(),
            'RandomForest': RandomForestRegressor(random_state=42),
            'XGBoost':      XGBRegressor(random_state=42, objective='reg:squarederror'),
        }

        # Grids: filtramos 'random_state' y 'objective' (no son hiperparámetros de búsqueda)
        grids = {}
        for nombre in modelos_base:
            g = {k: v for k, v in ml_cfg['modelos'][nombre].items()
                 if k not in ('random_state', 'objective')}
            grids[nombre] = g

        mejores_modelos: Dict[str, Any] = {}
        mejores_scores: Dict[str, float] = {}

        for nombre, modelo in modelos_base.items():
            grid = GridSearchCV(
                modelo, grids[nombre], cv=cv,
                scoring=scoring, n_jobs=n_jobs,
            )
            grid.fit(X_train_pca, residuo_train)
            mejores_modelos[nombre] = grid.best_estimator_
            mejores_scores[nombre] = float(-grid.best_score_)

        campeon_name = min(mejores_scores, key=mejores_scores.get)
        log.info("  ML competition: %s. Scores: %s",
                 campeon_name,
                 {k: round(v, 3) for k, v in mejores_scores.items()})
        return campeon_name, mejores_modelos[campeon_name], mejores_scores

    # ------------------------------------------------------------------
    # Entrenar un target (celda 49 completo)
    # ------------------------------------------------------------------
    def train_one(self,
                  df_paper: pd.DataFrame,
                  target: str,
                  vars_ambientales: List[str],
                  horizon: int,
                  variant: str = 'Lags',
                  dir_prod: Optional[str] = None,
                  dir_out: Optional[str] = None,
                  save_artifacts: bool = True,
                  save_plots: bool = True) -> Dict:
        """
        Entrena un target completo. Devuelve un dict con métricas + paths.

        Réplica 1:1 de celda 49 (loop interno).
        """
        # Saltar si todos ceros (celda 49 §skip)
        if (df_paper[target] == 0).all():
            log.info("  -> SKIP %s (todos ceros)", target)
            return {'target': target, 'skipped': True, 'reason': 'all_zeros'}

        sf = safe_filename(target)
        tc = target_clean(target)
        log.info(" -> Evaluando: %s", tc)

        # Split (celda 49 §split)
        y_all = df_paper[target].values
        y_train, y_test = y_all[:-horizon], y_all[-horizon:]
        X_train_env = df_paper[vars_ambientales].iloc[:-horizon]
        X_test_env = df_paper[vars_ambientales].iloc[-horizon:]

        # A: Chronos rolling
        pred_chronos_test = self.chronos_rolling(y_train, y_test, horizon)

        # Residuo train (celda 49 §residuo): y_train - rolling(4).mean()
        rw = self.cfg.train.rolling_window_residuo
        residuo_train = y_train - pd.Series(y_train).rolling(window=rw, min_periods=1).mean().values

        # B: Scaler + PCA (sin fuga)
        from sklearn.preprocessing import StandardScaler
        from sklearn.decomposition import PCA

        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train_env)
        X_test_scaled = scaler.transform(X_test_env)

        pca_cfg = self.cfg.train.pca
        pca = PCA(n_components=pca_cfg['n_components'], random_state=pca_cfg['random_state'])
        X_train_pca = pca.fit_transform(X_train_scaled)
        X_test_pca = pca.transform(X_test_scaled)
        num_componentes = pca.n_components_

        # C: ML competition
        campeon_name, modelo_campeon, scores = self._ml_competition(
            X_train_pca, residuo_train
        )

        # D: Métricas
        pred_hibrida = np.maximum(
            pred_chronos_test + modelo_campeon.predict(X_test_pca), 0
        )
        wmape_chronos = wmape(y_test, pred_chronos_test)
        wmape_hibrido = wmape(y_test, pred_hibrida)
        from sklearn.metrics import mean_absolute_error
        mae_hibrido = float(mean_absolute_error(y_test, pred_hibrida))

        log.info("  %s | PCA=%d comp | %s | WMAPE Chronos=%.2f, Hibrido=%.2f",
                 tc, num_componentes, campeon_name, wmape_chronos, wmape_hibrido)

        # E: Exportar modelos (celda 49 §E)
        paths = {}
        if save_artifacts and dir_prod:
            os.makedirs(dir_prod, exist_ok=True)
            paths['scaler'] = os.path.join(dir_prod, f'Scaler_{sf}.pkl')
            paths['pca'] = os.path.join(dir_prod, f'PCA_{sf}.pkl')
            paths['modelo'] = os.path.join(dir_prod, f'{campeon_name}_Hybrid_{sf}.pkl')
            joblib.dump(scaler, paths['scaler'])
            joblib.dump(pca, paths['pca'])
            joblib.dump(modelo_campeon, paths['modelo'])
            log.info("  Exportados: Scaler/PCA/%s_Hybrid → %s", campeon_name, dir_prod)

        # F: Gráficos (celda 49 §F)
        if save_plots and dir_out:
            os.makedirs(dir_out, exist_ok=True)
            self._plot_forecast(
                y_test, pred_chronos_test, pred_hibrida,
                tc, num_componentes, campeon_name, variant,
                os.path.join(dir_out, f'Forecast_{variant}_{sf}.png'),
            )
            self._plot_features(
                X_train_scaled, residuo_train, vars_ambientales,
                tc, variant,
                os.path.join(dir_out, f'Features_{variant}_{sf}.png'),
            )

        return {
            'target': tc,
            'safe_filename': sf,
            'skipped': False,
            'campeon': campeon_name,
            'componentes_pca': int(num_componentes),
            'mae_hibrido': round(mae_hibrido, 2),
            'wmape_chronos': round(wmape_chronos, 2),
            'wmape_hibrido': round(wmape_hibrido, 2),
            'ml_scores': {k: round(v, 3) for k, v in scores.items()},
            'paths': paths,
        }

    # ------------------------------------------------------------------
    # Plots
    # ------------------------------------------------------------------
    def _plot_forecast(self, y_test, pred_chronos, pred_hibrida,
                       tc, n_comp, campeon, variant, path):
        import matplotlib.pyplot as plt
        plt.figure(figsize=(12, 5))
        x = range(len(y_test))
        plt.plot(x, y_test, 'k-o', label='Real', markersize=4)
        plt.plot(x, pred_chronos, 'b--', label='Chronos T5', linewidth=2)
        plt.plot(x, pred_hibrida, 'r-', linewidth=2,
                 label=f'Hybrid ({campeon})')
        plt.title(f'Hybrid Model ({variant}): {tc}\nPCA ({n_comp} comp) + {campeon}')
        plt.xlabel('Validation Weeks')
        plt.ylabel('Consultation Volume')
        plt.legend()
        plt.grid(alpha=0.3)
        plt.tight_layout()
        plt.savefig(path, dpi=300)
        plt.close()

    def _plot_features(self, X_train_scaled, residuo_train,
                       vars_ambientales, tc, variant, path):
        import matplotlib.pyplot as plt
        import seaborn as sns
        from sklearn.ensemble import RandomForestRegressor

        rf = RandomForestRegressor(n_estimators=100, max_depth=5, random_state=42)
        rf.fit(X_train_scaled, residuo_train)
        imp = pd.DataFrame({
            'Feature': vars_ambientales,
            'Importance': rf.feature_importances_ * 100,
        }).sort_values('Importance', ascending=False).head(10)

        plt.figure(figsize=(8, 4))
        sns.barplot(data=imp, x='Importance', y='Feature', palette='magma')
        plt.title(f'Top Environmental Drivers ({variant})\n{tc}')
        plt.tight_layout()
        plt.savefig(path, dpi=300)
        plt.close()

    # ------------------------------------------------------------------
    # Entrenar todos los targets (loop principal de celda 49)
    # ------------------------------------------------------------------
    def train_all(self,
                  df_modelos: pd.DataFrame,
                  variant: str = 'lags',
                  save_artifacts: bool = True,
                  save_plots: bool = True) -> Tuple[pd.DataFrame, str]:
        """
        Entrena los 13 targets. Devuelve (df_metricas, csv_path).

        variant: 'lags' o 'nolags'. Determina subdir de salida.
        """
        usar_lags = (variant == 'lags')
        tipo = 'Lags' if usar_lags else 'NoLags'
        dir_prod = self.cfg.output_path('modelos_lags' if usar_lags else 'modelos_nolags')
        dir_out = self.cfg.output_path('resultados_lags' if usar_lags else 'resultados_nolags')

        df_paper, cols_epi, vars_amb, horizon = self._prepare_data(df_modelos, usar_lags)

        resultados = []
        for target in cols_epi:
            r = self.train_one(
                df_paper, target, vars_amb, horizon,
                variant=tipo, dir_prod=dir_prod, dir_out=dir_out,
                save_artifacts=save_artifacts, save_plots=save_plots,
            )
            resultados.append(r)

        # Métricas finales (celda 49 §df_res)
        df_res = pd.DataFrame([
            {k: v for k, v in r.items() if k in
             ('target', 'campeon', 'componentes_pca', 'mae_hibrido',
              'wmape_chronos', 'wmape_hibrido')}
            for r in resultados if not r.get('skipped')
        ])
        df_res = df_res.rename(columns={
            'target': 'Target',
            'campeon': 'Mejor_Modelo',
            'componentes_pca': 'Componentes_PCA',
            'mae_hibrido': 'MAE_Hibrido',
            'wmape_chronos': 'WMAPE_Chronos',
            'wmape_hibrido': 'WMAPE_Hibrido',
        })

        csv_path = os.path.join(dir_out, f'Metricas_Finales_{tipo}.csv')
        os.makedirs(dir_out, exist_ok=True)
        df_res.to_csv(csv_path, index=False)
        log.info("HZF: %s. %d targets entrenados. Métricas → %s",
                 tipo, len(df_res), csv_path)
        return df_res, csv_path


# ---------------------------------------------------------------------------
# Inference (carga trio + predicción)
# ---------------------------------------------------------------------------

class HZFInference:
    """Carga un trío (Scaler+PCA+{Campeon}_Hybrid) y predice."""

    def __init__(self, cfg: Config, models_dir: Optional[str] = None):
        self.cfg = cfg
        self.models_dir = models_dir or cfg.output_path('modelos_lags')
        self._chronos = None

    def _load_chronos(self):
        if self._chronos is None:
            import torch
            from chronos import ChronosPipeline
            ch = self.cfg.train.chronos
            dtype = getattr(torch, ch['torch_dtype'])
            self._chronos = ChronosPipeline.from_pretrained(
                ch['model_name'], device_map=ch['device_map'], torch_dtype=dtype,
            )
        return self._chronos

    def _find_champion_name(self, sf: str) -> Optional[str]:
        """Busca el archivo {Campeon}_Hybrid_{sf}.pkl y devuelve el nombre del campeón."""
        if not os.path.isdir(self.models_dir):
            return None
        suffix = f'_Hybrid_{sf}.pkl'
        for fn in os.listdir(self.models_dir):
            if fn.endswith(suffix) and not fn.startswith(('Scaler_', 'PCA_')):
                return fn.replace(suffix, '')
        return None

    def load_trio(self, target: str) -> Dict:
        """Carga (scaler, pca, modelo, champion_name) para un target."""
        sf = safe_filename(target)
        champion = self._find_champion_name(sf)
        if champion is None:
            raise FileNotFoundError(
                f"No se encontró modelo para {target} en {self.models_dir} "
                f"(buscando *_Hybrid_{sf}.pkl)"
            )
        return {
            'scaler': joblib.load(os.path.join(self.models_dir, f'Scaler_{sf}.pkl')),
            'pca':    joblib.load(os.path.join(self.models_dir, f'PCA_{sf}.pkl')),
            'modelo': joblib.load(os.path.join(self.models_dir, f'{champion}_Hybrid_{sf}.pkl')),
            'champion': champion,
        }

    def predict(self,
                target: str,
                y_history: np.ndarray,
                X_env_current: np.ndarray,
                horizon: int) -> Dict:
        """
        Predicción híbrida para `horizon` semanas.

        Parámetros
        ----------
        target : nombre de la columna target (ej. 'Total_Consultations').
        y_history : histórico del target (np.array, >= horizon+4 semanas).
        X_env_current : variables ambientales (con lags ya armados) para las
                        `horizon` semanas a predecir. Shape (horizon, n_vars_amb).
        horizon : número de semanas a predecir.

        Devuelve
        --------
        Dict con claves: chronos, ml_correction, hybrid, champion, wmape_floor.
        """
        trio = self.load_trio(target)

        # 1. Chronos rolling (sin y_test conocido → ctx fija = y_history)
        #    Nota: en inference pura no hay y_test, así que ctx = y_history y
        #    predecimos `horizon` semanas en un solo bloque.
        import torch
        ch = self.cfg.train.chronos
        pipeline = self._load_chronos()
        forecast = pipeline.predict(
            torch.tensor(y_history),
            prediction_length=horizon,
            num_samples=ch['num_samples'],
        )
        pred_chronos = np.quantile(forecast[0].numpy(), ch['quantile'], axis=0)

        # 2. ML correction
        X_scaled = trio['scaler'].transform(X_env_current)
        X_pca = trio['pca'].transform(X_scaled)
        pred_ml = trio['modelo'].predict(X_pca)

        # 3. Híbrido
        pred_hibrida = np.maximum(pred_chronos + pred_ml, 0)

        return {
            'chronos': pred_chronos,
            'ml_correction': pred_ml,
            'hybrid': pred_hibrida,
            'champion': trio['champion'],
        }
