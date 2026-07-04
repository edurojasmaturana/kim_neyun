"""Tests del flujo de aceptación de invitaciones (api/invitations.py).

Cubre GET y POST /invitaciones/aceptar con SQLite en memoria.

Regresión histórica: TypeError en _valid_invitation cuando expires_at
(naive desde Aurora Data API) se comparaba con _utcnow() (aware). Se verifica
que un token válido devuelva 200, no 500.
"""

import datetime
import secrets

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import invitations
from api.invitations import hash_token
from shared.users_db import Invitation


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def inv_client(db_sessionmaker, monkeypatch):
    """App mínima con el router de invitaciones sobre SQLite en memoria.

    invitations.py llama get_sessionmaker()() directamente (sin FastAPI DI),
    así que lo parchamos en el módulo para apuntar al SQLite de tests.
    """
    app = FastAPI()
    app.include_router(invitations.router)
    monkeypatch.setattr("api.invitations.get_sessionmaker", lambda: db_sessionmaker)
    return TestClient(app)


def _inv(db_sessionmaker, *, email="inv@test.cl", role="viewer",
         hours_ahead=24, accepted=False):
    """Inserta una invitación con datetimes naive (como devuelve Aurora Data API)."""
    raw = secrets.token_urlsafe(32)
    now = datetime.datetime.utcnow()
    inv = Invitation(
        email=email,
        role=role,
        token_hash=hash_token(raw),
        expires_at=now + datetime.timedelta(hours=hours_ahead),
        accepted_at=now if accepted else None,
        created_by="admin@test.cl",
        created_at=now,
    )
    s = db_sessionmaker()
    s.add(inv)
    s.commit()
    s.close()
    return raw


# ---------------------------------------------------------------------------
# GET /invitaciones/aceptar
# ---------------------------------------------------------------------------

class TestAceptarForm:
    def test_token_valido_muestra_formulario(self, inv_client, db_sessionmaker):
        """Regresión TypeError: expires_at naive vs _utcnow() aware → debe ser 200."""
        raw = _inv(db_sessionmaker)
        r = inv_client.get(f"/invitaciones/aceptar?token={raw}")
        assert r.status_code == 200
        assert "Activar cuenta" in r.text

    def test_token_invalido_da_400(self, inv_client):
        r = inv_client.get("/invitaciones/aceptar?token=token-que-no-existe")
        assert r.status_code == 400

    def test_sin_token_da_400(self, inv_client):
        r = inv_client.get("/invitaciones/aceptar")
        assert r.status_code == 400

    def test_token_vencido_da_410(self, inv_client, db_sessionmaker):
        raw = _inv(db_sessionmaker, hours_ahead=-1)
        r = inv_client.get(f"/invitaciones/aceptar?token={raw}")
        assert r.status_code == 410
        assert "caducado" in r.text

    def test_invitacion_ya_usada_da_410(self, inv_client, db_sessionmaker):
        raw = _inv(db_sessionmaker, accepted=True)
        r = inv_client.get(f"/invitaciones/aceptar?token={raw}")
        assert r.status_code == 410
        assert "utilizada" in r.text


# ---------------------------------------------------------------------------
# POST /invitaciones/aceptar
# ---------------------------------------------------------------------------

class TestAceptarSubmit:
    def test_acepta_crea_usuario_y_da_200(self, inv_client, db_sessionmaker):
        """Flujo feliz: token válido + passwords coincidentes → cuenta creada."""
        raw = _inv(db_sessionmaker, email="nuevo@test.cl")
        r = inv_client.post(
            "/invitaciones/aceptar",
            data={"token": raw, "password": "Password123!", "password2": "Password123!"},
        )
        assert r.status_code == 200
        assert "Cuenta creada" in r.text
        assert "nuevo@test.cl" in r.text

    def test_passwords_no_coinciden_da_400(self, inv_client, db_sessionmaker):
        raw = _inv(db_sessionmaker, email="p1@test.cl")
        r = inv_client.post(
            "/invitaciones/aceptar",
            data={"token": raw, "password": "Password123!", "password2": "Diferente456!"},
        )
        assert r.status_code == 400
        assert "no coinciden" in r.text

    def test_password_corta_da_400(self, inv_client, db_sessionmaker):
        raw = _inv(db_sessionmaker, email="p2@test.cl")
        r = inv_client.post(
            "/invitaciones/aceptar",
            data={"token": raw, "password": "corta", "password2": "corta"},
        )
        assert r.status_code == 400

    def test_token_invalido_da_400(self, inv_client):
        r = inv_client.post(
            "/invitaciones/aceptar",
            data={"token": "no-existe", "password": "Password123!", "password2": "Password123!"},
        )
        assert r.status_code == 400

    def test_invitacion_ya_usada_da_410(self, inv_client, db_sessionmaker):
        raw = _inv(db_sessionmaker, email="usada@test.cl", accepted=True)
        r = inv_client.post(
            "/invitaciones/aceptar",
            data={"token": raw, "password": "Password123!", "password2": "Password123!"},
        )
        assert r.status_code == 410

    def test_token_vencido_da_410(self, inv_client, db_sessionmaker):
        raw = _inv(db_sessionmaker, email="venc@test.cl", hours_ahead=-1)
        r = inv_client.post(
            "/invitaciones/aceptar",
            data={"token": raw, "password": "Password123!", "password2": "Password123!"},
        )
        assert r.status_code == 410

    def test_segunda_aceptacion_del_mismo_token_da_410(self, inv_client, db_sessionmaker):
        """El token es de un solo uso: el segundo intento con el mismo token da 410."""
        raw = _inv(db_sessionmaker, email="singleuse@test.cl")
        inv_client.post(
            "/invitaciones/aceptar",
            data={"token": raw, "password": "Password123!", "password2": "Password123!"},
        )
        r = inv_client.post(
            "/invitaciones/aceptar",
            data={"token": raw, "password": "OtraPass123!", "password2": "OtraPass123!"},
        )
        assert r.status_code == 410
