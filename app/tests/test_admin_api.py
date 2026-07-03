"""Tests del router de administración JSON (api/admin_api.py).

Estrategia:
- App mínima con auth.router + admin_api.router + SQLite en memoria.
- El envío de correo (send_invitation_email) se mockea en todos los tests
  para no depender de SES ni de AWS.
- Se prueban los 3 endpoints: POST /admin/invitar, GET /admin/users,
  PATCH /admin/users/{user_id}.
"""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import admin_api, auth
from shared.users_db import get_session


# ---------------------------------------------------------------------------
# Fixture: cliente con SQLite en memoria y semilla de usuarios
# ---------------------------------------------------------------------------

@pytest.fixture
def client(db_sessionmaker, make_user):
    """App con auth + admin_api; BD SQLite sobreescrita; 2 usuarios semilla."""
    app = FastAPI()
    app.include_router(auth.router)
    app.include_router(admin_api.router)

    def _session():
        s = db_sessionmaker()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = _session

    s = db_sessionmaker()
    s.add(make_user(email="admin@kim-neyun.cl", password="admin12345", role="admin"))
    s.add(make_user(email="viewer@kim-neyun.cl", password="viewer12345", role="viewer"))
    s.commit()
    s.close()

    return TestClient(app)


def _token(client, email, password):
    r = client.post("/auth/login", data={"username": email, "password": password})
    return r.json()["access_token"]


def _admin_headers(client):
    return {"Authorization": f"Bearer {_token(client, 'admin@kim-neyun.cl', 'admin12345')}"}


def _viewer_headers(client):
    return {"Authorization": f"Bearer {_token(client, 'viewer@kim-neyun.cl', 'viewer12345')}"}


# ---------------------------------------------------------------------------
# POST /admin/invitar
# ---------------------------------------------------------------------------

class TestInvitar:
    def test_admin_crea_invitacion_sin_ses(self, client):
        """Sin SES_FROM_EMAIL configurado el endpoint igual devuelve 201 + link."""
        with patch("api.admin_api.send_invitation_email", return_value=False) as mock_send:
            r = client.post(
                "/admin/invitar",
                json={"email": "nuevo@hospital.cl", "role": "viewer"},
                headers=_admin_headers(client),
            )
        assert r.status_code == 201
        body = r.json()
        assert body["ok"] is True
        assert body["email"] == "nuevo@hospital.cl"
        assert body["role"] == "viewer"
        assert "/invitaciones/aceptar?token=" in body["link"]
        assert body["email_enviado"] is False
        mock_send.assert_called_once()

    def test_admin_crea_invitacion_con_ses(self, client):
        """Con SES configurado el endpoint devuelve email_enviado=True."""
        with patch("api.admin_api.send_invitation_email", return_value=True):
            r = client.post(
                "/admin/invitar",
                json={"email": "nuevo2@hospital.cl", "role": "admin"},
                headers=_admin_headers(client),
            )
        assert r.status_code == 201
        assert r.json()["email_enviado"] is True
        assert r.json()["role"] == "admin"

    def test_viewer_no_puede_invitar(self, client):
        with patch("api.admin_api.send_invitation_email", return_value=False):
            r = client.post(
                "/admin/invitar",
                json={"email": "otro@hospital.cl", "role": "viewer"},
                headers=_viewer_headers(client),
            )
        assert r.status_code == 403

    def test_sin_auth_da_401(self, client):
        r = client.post("/admin/invitar", json={"email": "x@x.cl", "role": "viewer"})
        assert r.status_code == 401

    def test_email_duplicado_da_409(self, client):
        """Invitar a alguien que ya tiene cuenta devuelve 409."""
        with patch("api.admin_api.send_invitation_email", return_value=False):
            r = client.post(
                "/admin/invitar",
                json={"email": "viewer@kim-neyun.cl", "role": "viewer"},
                headers=_admin_headers(client),
            )
        assert r.status_code == 409

    def test_rol_invalido_da_422(self, client):
        r = client.post(
            "/admin/invitar",
            json={"email": "x@x.cl", "role": "superuser"},
            headers=_admin_headers(client),
        )
        assert r.status_code == 422

    def test_email_invalido_da_422(self, client):
        r = client.post(
            "/admin/invitar",
            json={"email": "no-es-un-email", "role": "viewer"},
            headers=_admin_headers(client),
        )
        assert r.status_code == 422

    def test_send_email_se_llama_con_args_correctos(self, client):
        """Verifica que los argumentos al servicio de email son los esperados."""
        with patch("api.admin_api.send_invitation_email", return_value=True) as mock_send:
            client.post(
                "/admin/invitar",
                json={"email": "destinatario@hospital.cl", "role": "viewer"},
                headers=_admin_headers(client),
            )
        call_kwargs = mock_send.call_args
        assert call_kwargs.kwargs["to_email"] == "destinatario@hospital.cl"
        assert call_kwargs.kwargs["role"] == "viewer"
        assert call_kwargs.kwargs["invited_by"] == "admin@kim-neyun.cl"
        assert "/invitaciones/aceptar?token=" in call_kwargs.kwargs["link"]


# ---------------------------------------------------------------------------
# GET /admin/users
# ---------------------------------------------------------------------------

class TestListarUsuarios:
    def test_admin_obtiene_lista(self, client):
        r = client.get("/admin/users", headers=_admin_headers(client))
        assert r.status_code == 200
        emails = [u["email"] for u in r.json()]
        assert "admin@kim-neyun.cl" in emails
        assert "viewer@kim-neyun.cl" in emails

    def test_viewer_no_puede_listar(self, client):
        assert client.get("/admin/users", headers=_viewer_headers(client)).status_code == 403

    def test_sin_auth_da_401(self, client):
        assert client.get("/admin/users").status_code == 401

    def test_estructura_de_usuario(self, client):
        r = client.get("/admin/users", headers=_admin_headers(client))
        user = r.json()[0]
        assert set(user.keys()) >= {"id", "email", "full_name", "role", "is_active"}


# ---------------------------------------------------------------------------
# PATCH /admin/users/{user_id}
# ---------------------------------------------------------------------------

class TestActualizarUsuario:
    def _get_viewer_id(self, client):
        users = client.get("/admin/users", headers=_admin_headers(client)).json()
        return next(u["id"] for u in users if u["email"] == "viewer@kim-neyun.cl")

    def test_admin_cambia_rol(self, client):
        uid = self._get_viewer_id(client)
        r = client.patch(
            f"/admin/users/{uid}",
            json={"role": "admin"},
            headers=_admin_headers(client),
        )
        assert r.status_code == 200
        assert r.json()["role"] == "admin"

    def test_admin_desactiva_usuario(self, client):
        uid = self._get_viewer_id(client)
        r = client.patch(
            f"/admin/users/{uid}",
            json={"is_active": False},
            headers=_admin_headers(client),
        )
        assert r.status_code == 200
        assert r.json()["is_active"] is False

    def test_patch_parcial_solo_cambia_campos_enviados(self, client):
        uid = self._get_viewer_id(client)
        r = client.patch(
            f"/admin/users/{uid}",
            json={"role": "admin"},
            headers=_admin_headers(client),
        )
        assert r.json()["role"] == "admin"
        assert r.json()["is_active"] is True  # no se tocó

    def test_usuario_inexistente_da_404(self, client):
        r = client.patch(
            "/admin/users/uid-que-no-existe",
            json={"role": "viewer"},
            headers=_admin_headers(client),
        )
        assert r.status_code == 404

    def test_viewer_no_puede_actualizar(self, client):
        uid = self._get_viewer_id(client)
        r = client.patch(
            f"/admin/users/{uid}",
            json={"role": "admin"},
            headers=_viewer_headers(client),
        )
        assert r.status_code == 403

    def test_sin_auth_da_401(self, client):
        assert client.patch("/admin/users/cualquier-id", json={"role": "viewer"}).status_code == 401

    def test_rol_invalido_da_422(self, client):
        uid = self._get_viewer_id(client)
        r = client.patch(
            f"/admin/users/{uid}",
            json={"role": "superuser"},
            headers=_admin_headers(client),
        )
        assert r.status_code == 422
