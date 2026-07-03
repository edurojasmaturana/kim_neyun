"""Tests de la API (api/main.py) con TestClient.

Se sobreescribe la autenticación (get_current_user) y se mockea el repositorio
para aislar la lógica de los endpoints de DynamoDB y de la BD de usuarios.
"""

import pytest
from fastapi.testclient import TestClient

from api import main
from api.auth import get_current_user
from shared import repository
from shared.catalog import HOSPITALES
from shared.users_db import User, get_session


@pytest.fixture
def client():
    app = main.app
    app.dependency_overrides[get_current_user] = lambda: User(
        id="uid", email="t@kim-neyun.cl", password_hash="x", full_name="T",
        role="viewer", is_active=True,
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- /health (sin auth) ------------------------------------------------------

def test_health_no_requiere_auth():
    r = TestClient(main.app).get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# --- /health/db (sin auth, warmup de Aurora) ---------------------------------

def test_health_db_sin_bd_devuelve_json_503():
    """Sin BD configurada devuelve 503 JSON — nunca texto plano ni body vacío."""
    r = TestClient(main.app).get("/health/db")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "unavailable"
    assert body["db"] == "resuming"


def test_health_db_con_bd_devuelve_ok(db_sessionmaker, monkeypatch):
    """Con BD disponible (simulada con SQLite) devuelve 200 {"status":"ok","db":"up"}."""
    # get_sessionmaker ya fue importado en main; hay que patchear la referencia local.
    monkeypatch.setattr(main, "get_sessionmaker", lambda: db_sessionmaker)

    r = TestClient(main.app).get("/health/db")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] == "up"


# --- /hospitales -------------------------------------------------------------

def test_hospitales_requiere_auth():
    # Sin override: el TestClient limpio no trae token.
    assert TestClient(main.app).get("/hospitales").status_code == 401


def test_hospitales_devuelve_catalogo(client):
    r = client.get("/hospitales")
    assert r.status_code == 200
    assert r.json() == {"hospitales": HOSPITALES}


# --- /predecir ---------------------------------------------------------------

class TestPredecir:
    def test_ok_serializa_anio_con_tilde(self, client, monkeypatch):
        monkeypatch.setattr(repository, "get_prediccion_semana", lambda *a, **k: {
            "hospital": "Hospital X", "semana_epi": 24, "anio": 2026,
            "estimaciones": {"Causas": {"Pneumonia": 42.0}, "Edades": {"65oMas": 73.0}, "Total": 42.0},
            "temp_ref": 8.4, "nivel_alerta": "CRITICO",
        })
        r = client.post("/predecir", json={
            "EstablecimientoGlosa": "Hospital X", "fecha_referencia": "2026-06-10",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["año"] == 2026          # alias del PoC
        assert "anio" not in body
        assert body["nivel_alerta"] == "CRITICO"
        assert body["temperatura_referencia"] == 8.4

    def test_fecha_invalida_da_422(self, client):
        r = client.post("/predecir", json={
            "EstablecimientoGlosa": "Hospital X", "fecha_referencia": "10-06-2026",
        })
        assert r.status_code == 422

    def test_sin_prediccion_da_404(self, client, monkeypatch):
        monkeypatch.setattr(repository, "get_prediccion_semana", lambda *a, **k: None)
        r = client.post("/predecir", json={
            "EstablecimientoGlosa": "Hospital X", "fecha_referencia": "2026-06-10",
        })
        assert r.status_code == 404


# --- /proyeccion_anual -------------------------------------------------------

class TestProyeccionAnual:
    def test_ok(self, client, monkeypatch):
        monkeypatch.setattr(repository, "get_proyeccion_anual", lambda *a, **k: {
            "hospital": "Hospital X", "anio": 2026, "semanas": [1, 2, 3],
            "curva_ia": [120.0, 135.0, 150.0], "curva_real": [118, 130, None],
        })
        r = client.post("/proyeccion_anual", json={
            "EstablecimientoGlosa": "Hospital X", "anio_proyeccion": 2026,
        })
        assert r.status_code == 200
        body = r.json()
        assert body["anio_proyectado"] == 2026
        assert body["curva_real"] == [118, 130, None]

    def test_sin_proyeccion_da_404(self, client, monkeypatch):
        monkeypatch.setattr(repository, "get_proyeccion_anual", lambda *a, **k: None)
        r = client.post("/proyeccion_anual", json={
            "EstablecimientoGlosa": "Hospital X", "anio_proyeccion": 2099,
        })
        assert r.status_code == 404
