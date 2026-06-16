"""Tests de autenticación (api/auth.py): hashing, JWT, dependencias y endpoints."""

import datetime

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import auth
from shared import config
from shared.users_db import get_session


# --- Hashing -----------------------------------------------------------------

def test_hash_password_verifica_ida_y_vuelta():
    h = auth.hash_password("secreto-largo")
    assert h != "secreto-largo"          # no se guarda en claro
    assert auth.verify_password("secreto-largo", h) is True
    assert auth.verify_password("otra", h) is False


# --- create_access_token -----------------------------------------------------

def test_create_access_token_contiene_claims(make_user):
    user = make_user(email="a@b.cl", role="admin")
    user.id = "uid-123"
    token = auth.create_access_token(user)
    payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALG])
    assert payload["sub"] == "uid-123"
    assert payload["email"] == "a@b.cl"
    assert payload["role"] == "admin"
    assert payload["exp"] > payload["iat"]


# --- get_current_user --------------------------------------------------------

class TestGetCurrentUser:
    def test_token_valido_devuelve_usuario(self, session, make_user):
        user = make_user()
        session.add(user)
        session.commit()
        token = auth.create_access_token(user)
        assert auth.get_current_user(token=token, session=session).id == user.id

    def test_token_corrupto_da_401(self, session):
        with pytest.raises(Exception) as exc:
            auth.get_current_user(token="no-es-un-jwt", session=session)
        assert exc.value.status_code == 401

    def test_token_sin_sub_da_401(self, session):
        token = jwt.encode({"email": "x@y.cl"}, config.JWT_SECRET, algorithm=config.JWT_ALG)
        with pytest.raises(Exception) as exc:
            auth.get_current_user(token=token, session=session)
        assert exc.value.status_code == 401

    def test_usuario_inexistente_da_401(self, session, make_user):
        user = make_user()  # no se agrega a la sesión
        token = auth.create_access_token(user)
        with pytest.raises(Exception) as exc:
            auth.get_current_user(token=token, session=session)
        assert exc.value.status_code == 401

    def test_usuario_inactivo_da_401(self, session, make_user):
        user = make_user(is_active=False)
        session.add(user)
        session.commit()
        token = auth.create_access_token(user)
        with pytest.raises(Exception) as exc:
            auth.get_current_user(token=token, session=session)
        assert exc.value.status_code == 401

    def test_token_expirado_da_401(self, session, make_user):
        user = make_user()
        session.add(user)
        session.commit()
        past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
        token = jwt.encode(
            {"sub": user.id, "exp": past}, config.JWT_SECRET, algorithm=config.JWT_ALG
        )
        with pytest.raises(Exception) as exc:
            auth.get_current_user(token=token, session=session)
        assert exc.value.status_code == 401


# --- require_admin -----------------------------------------------------------

class TestRequireAdmin:
    def test_admin_pasa(self, make_user):
        admin = make_user(role="admin")
        assert auth.require_admin(current=admin) is admin

    def test_viewer_da_403(self, make_user):
        viewer = make_user(role="viewer")
        with pytest.raises(Exception) as exc:
            auth.require_admin(current=viewer)
        assert exc.value.status_code == 403


# --- Endpoints (TestClient con SQLite) --------------------------------------

@pytest.fixture
def client(db_sessionmaker, make_user):
    """App mínima con el router de auth y la BD sobreescrita por SQLite."""
    app = FastAPI()
    app.include_router(auth.router)

    def _session_override():
        s = db_sessionmaker()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = _session_override

    # Semilla: un admin y un viewer.
    s = db_sessionmaker()
    s.add(make_user(email="admin@kim-neyun.cl", password="admin12345", role="admin"))
    s.add(make_user(email="viewer@kim-neyun.cl", password="viewer12345", role="viewer"))
    s.commit()
    s.close()

    return TestClient(app)


def _login(client, email, password):
    return client.post("/auth/login", data={"username": email, "password": password})


class TestLogin:
    def test_login_correcto_devuelve_token(self, client):
        r = _login(client, "admin@kim-neyun.cl", "admin12345")
        assert r.status_code == 200
        assert r.json()["token_type"] == "bearer"
        assert r.json()["access_token"]

    def test_email_insensible_a_mayusculas(self, client):
        r = _login(client, "ADMIN@KIM-NEYUN.CL", "admin12345")
        assert r.status_code == 200

    def test_password_incorrecta_da_401(self, client):
        r = _login(client, "admin@kim-neyun.cl", "mala")
        assert r.status_code == 401

    def test_usuario_inexistente_da_401(self, client):
        r = _login(client, "nadie@kim-neyun.cl", "loquesea")
        assert r.status_code == 401


class TestMe:
    def test_me_con_token(self, client):
        token = _login(client, "viewer@kim-neyun.cl", "viewer12345").json()["access_token"]
        r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["email"] == "viewer@kim-neyun.cl"
        assert r.json()["role"] == "viewer"

    def test_me_sin_token_da_401(self, client):
        assert client.get("/auth/me").status_code == 401


class TestCrearUsuario:
    def _auth(self, client, email, password):
        token = _login(client, email, password).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_admin_crea_usuario(self, client):
        r = client.post(
            "/auth/users",
            json={"email": "nuevo@kim-neyun.cl", "password": "nuevo12345", "role": "viewer"},
            headers=self._auth(client, "admin@kim-neyun.cl", "admin12345"),
        )
        assert r.status_code == 201
        assert r.json()["email"] == "nuevo@kim-neyun.cl"

    def test_viewer_no_puede_crear_403(self, client):
        r = client.post(
            "/auth/users",
            json={"email": "x@kim-neyun.cl", "password": "x12345678"},
            headers=self._auth(client, "viewer@kim-neyun.cl", "viewer12345"),
        )
        assert r.status_code == 403

    def test_email_duplicado_da_409(self, client):
        r = client.post(
            "/auth/users",
            json={"email": "viewer@kim-neyun.cl", "password": "otra12345"},
            headers=self._auth(client, "admin@kim-neyun.cl", "admin12345"),
        )
        assert r.status_code == 409

    def test_password_corta_da_422(self, client):
        r = client.post(
            "/auth/users",
            json={"email": "corto@kim-neyun.cl", "password": "1234"},
            headers=self._auth(client, "admin@kim-neyun.cl", "admin12345"),
        )
        assert r.status_code == 422

    def test_rol_invalido_da_422(self, client):
        r = client.post(
            "/auth/users",
            json={"email": "rol@kim-neyun.cl", "password": "rol12345678", "role": "superuser"},
            headers=self._auth(client, "admin@kim-neyun.cl", "admin12345"),
        )
        assert r.status_code == 422
