"""Tests del repositorio de DynamoDB (shared/repository.py) con moto.

moto simula DynamoDB en memoria; no se toca AWS. Se resetea la caché lru de
shared.db para que el recurso/cliente boto3 se cree dentro del mock.
"""

import pytest
from moto import mock_aws

from shared import db, repository


@pytest.fixture
def ddb():
    """DynamoDB simulado con la tabla del proyecto ya creada."""
    db.get_table.cache_clear()
    db.get_client.cache_clear()
    with mock_aws():
        repository.ensure_table()
        yield
    db.get_table.cache_clear()
    db.get_client.cache_clear()


# --- Claves de ordenamiento --------------------------------------------------

def test_sk_semana_rellena_a_dos_digitos():
    assert repository._sk_semana(2026, 3) == "SEM#2026#03"
    assert repository._sk_semana(2026, 24) == "SEM#2026#24"


def test_sk_proy():
    assert repository._sk_proy(2026) == "PROY#2026"


# --- ensure_table ------------------------------------------------------------

def test_ensure_table_es_idempotente(ddb):
    repository.ensure_table()  # segunda llamada no debe fallar
    assert db.get_client().describe_table(TableName="kim-neyun-predicciones")


# --- Predicción semanal ------------------------------------------------------

class TestPrediccionSemana:
    def test_roundtrip(self, ddb):
        estimaciones = {"Causas": {"Pneumonia": 42.0}, "Edades": {"65oMas": 73.0}, "Total": 42.0}
        repository.upsert_prediccion_semana(
            "Hospital X", 2026, 24, total=42, nivel_alerta="CRITICO",
            temp_ref=8.4, estimaciones=estimaciones,
        )
        got = repository.get_prediccion_semana("Hospital X", 2026, 24)
        assert got == {
            "hospital": "Hospital X",
            "anio": 2026,
            "semana_epi": 24,
            "total": 42,
            "nivel_alerta": "CRITICO",
            "temp_ref": 8.4,
            "estimaciones": estimaciones,
        }

    def test_inexistente_devuelve_none(self, ddb):
        assert repository.get_prediccion_semana("Hospital X", 2026, 1) is None

    def test_upsert_sobreescribe(self, ddb):
        repository.upsert_prediccion_semana("H", 2026, 5, 10, "NORMAL", 12.0, {})
        repository.upsert_prediccion_semana("H", 2026, 5, 99, "CRITICO", 3.0, {})
        got = repository.get_prediccion_semana("H", 2026, 5)
        assert got["total"] == 99
        assert got["nivel_alerta"] == "CRITICO"


# --- Proyección anual --------------------------------------------------------

class TestProyeccionAnual:
    def test_roundtrip(self, ddb):
        repository.upsert_proyeccion_anual(
            "Hospital X", 2026, semanas=[1, 2, 3],
            curva_ia=[120, 135, 150], curva_real=[118, 130, None], total_ia=405,
        )
        got = repository.get_proyeccion_anual("Hospital X", 2026)
        assert got["hospital"] == "Hospital X"
        assert got["anio"] == 2026
        assert got["semanas"] == [1, 2, 3]
        assert got["curva_ia"] == [120, 135, 150]
        assert got["curva_real"] == [118, 130, None]
        assert got["total_ia"] == 405

    def test_inexistente_devuelve_none(self, ddb):
        assert repository.get_proyeccion_anual("Hospital X", 2099) is None

    def test_semana_y_proyeccion_no_colisionan(self, ddb):
        """Misma pk (hospital) y año, distinta sk: no se pisan."""
        repository.upsert_prediccion_semana("H", 2026, 24, 42, "NORMAL", 8.0, {})
        repository.upsert_proyeccion_anual("H", 2026, [1], [10], [9], 10)
        assert repository.get_prediccion_semana("H", 2026, 24)["total"] == 42
        assert repository.get_proyeccion_anual("H", 2026)["total_ia"] == 10


# --- _get_item: tabla ausente ------------------------------------------------

def test_get_item_sin_tabla_devuelve_none():
    """Si la tabla no existe (ResourceNotFound), se trata como 'sin datos'."""
    db.get_table.cache_clear()
    with mock_aws():
        assert repository.get_prediccion_semana("H", 2026, 1) is None
    db.get_table.cache_clear()
