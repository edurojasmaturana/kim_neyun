"""Tests del semáforo de alerta (shared/alertas.py).

Lógica pura sobre el histórico semanal: no depende de torch, AWS ni BD.
"""

import numpy as np
import pandas as pd
import pytest

from shared import alertas, config


# --- clasificar --------------------------------------------------------------

class TestClasificar:
    def test_umbrales_explicitos(self):
        umbrales = (100.0, 200.0)  # (moderado, critico)
        assert alertas.clasificar(50, umbrales) == alertas.NIVEL_NORMAL
        assert alertas.clasificar(150, umbrales) == alertas.NIVEL_MODERADO
        assert alertas.clasificar(250, umbrales) == alertas.NIVEL_CRITICO

    def test_bordes_inclusivos(self):
        """El corte es `>=`: el valor igual al umbral entra en el nivel superior."""
        umbrales = (100.0, 200.0)
        assert alertas.clasificar(100, umbrales) == alertas.NIVEL_MODERADO
        assert alertas.clasificar(200, umbrales) == alertas.NIVEL_CRITICO
        assert alertas.clasificar(99.999, umbrales) == alertas.NIVEL_NORMAL

    def test_respaldo_global_cuando_umbrales_none(self):
        """Sin umbrales por centro usa ALERTA_THRESHOLD (crítico) y 70% (moderado)."""
        critico = config.ALERTA_THRESHOLD
        moderado = 0.7 * critico
        assert alertas.clasificar(critico, None) == alertas.NIVEL_CRITICO
        assert alertas.clasificar(moderado, None) == alertas.NIVEL_MODERADO
        assert alertas.clasificar(moderado - 1, None) == alertas.NIVEL_NORMAL


# --- umbrales_centro ---------------------------------------------------------

def _df(filas):
    """Construye el histórico mínimo que consume alertas (causa + claves temporales)."""
    return pd.DataFrame(filas)


def _fila(hospital, anio, semana, pneumonia=0, influenza=0):
    return {
        "EstablecimientoGlosa": hospital,
        "Anio": anio,
        "SemanaEstadistica": semana,
        "Cause_Pneumonia": pneumonia,
        "Cause_Influenza": influenza,
    }


class TestUmbralesCentro:
    def test_historia_insuficiente_devuelve_none(self):
        """Con menos de ALERTA_MIN_SEMANAS no se confía en los percentiles."""
        filas = [_fila("H", 2025, s, pneumonia=10) for s in range(1, config.ALERTA_MIN_SEMANAS)]
        df = _df(filas)
        assert alertas.umbrales_centro(df, "H", 2026, 1) is None

    def test_historia_suficiente_devuelve_percentiles(self):
        n = config.ALERTA_MIN_SEMANAS
        filas = [_fila("H", 2025, s, pneumonia=s) for s in range(1, n + 1)]
        df = _df(filas)
        res = alertas.umbrales_centro(df, "H", 2026, 1)
        assert res is not None
        moderado, critico = res
        totales = np.arange(1, n + 1)
        assert moderado == pytest.approx(np.percentile(totales, config.ALERTA_PCT_MODERADO))
        assert critico == pytest.approx(np.percentile(totales, config.ALERTA_PCT_CRITICO))
        assert moderado <= critico

    def test_solo_cuenta_historia_anterior_a_la_referencia(self):
        """Semanas en o después de la referencia no entran en el cálculo."""
        n = config.ALERTA_MIN_SEMANAS
        pasadas = [_fila("H", 2025, s, pneumonia=10) for s in range(1, n + 1)]
        futuras = [_fila("H", 2026, s, pneumonia=9999) for s in range(1, 5)]
        df = _df(pasadas + futuras)
        moderado, critico = alertas.umbrales_centro(df, "H", 2026, 1)
        # Todas las pasadas valen 10 -> ambos percentiles == 10 (las futuras se excluyen).
        assert critico == pytest.approx(10.0)

    def test_filtra_por_hospital(self):
        n = config.ALERTA_MIN_SEMANAS
        propio = [_fila("H", 2025, s, pneumonia=10) for s in range(1, n + 1)]
        ajeno = [_fila("OTRO", 2025, s, pneumonia=9999) for s in range(1, n + 1)]
        df = _df(propio + ajeno)
        _, critico = alertas.umbrales_centro(df, "H", 2026, 1)
        assert critico == pytest.approx(10.0)

    def test_suma_multiples_causas(self):
        n = config.ALERTA_MIN_SEMANAS
        filas = [_fila("H", 2025, s, pneumonia=5, influenza=5) for s in range(1, n + 1)]
        df = _df(filas)
        _, critico = alertas.umbrales_centro(df, "H", 2026, 1)
        assert critico == pytest.approx(10.0)  # 5 + 5 por semana
