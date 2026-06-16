"""Invariantes del catálogo de dominio (shared/catalog.py).

Son constantes copiadas del PoC; estos tests fijan los contratos que el resto
del backend asume (sin duplicados, traducciones completas, etc.).
"""

from shared import catalog


def test_todos_targets_es_la_union_ordenada():
    assert catalog.TODOS_TARGETS == catalog.TARGETS_NOLAGS + catalog.TARGETS_LAGS


def test_no_hay_targets_duplicados():
    assert len(catalog.TODOS_TARGETS) == len(set(catalog.TODOS_TARGETS))


def test_nolags_y_lags_son_disjuntos():
    assert set(catalog.TARGETS_NOLAGS).isdisjoint(catalog.TARGETS_LAGS)


def test_hospitales_sin_duplicados_y_no_vacio():
    assert catalog.HOSPITALES
    assert len(catalog.HOSPITALES) == len(set(catalog.HOSPITALES))


def test_cada_causa_target_tiene_traduccion():
    """Toda columna Cause_* debe poder mostrarse traducida en el dashboard."""
    causas = [t[len("Cause_"):] for t in catalog.TODOS_TARGETS if t.startswith("Cause_")]
    faltantes = [c for c in causas if c not in catalog.TRADUCCION_CAUSAS]
    assert faltantes == []


def test_traducciones_no_vacias():
    assert all(catalog.TRADUCCION_CAUSAS.values())
    assert all(catalog.TRADUCCION_EDADES.values())
