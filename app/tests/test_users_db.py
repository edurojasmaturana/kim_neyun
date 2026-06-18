"""Tests de la resiliencia al 'resuming' de Aurora Serverless v2 (scale-to-zero).

Con `min_capacity = 0` el cluster se pausa tras inactividad; la primera consulta
tras idle falla con DatabaseResumingException (envuelta por SQLAlchemy en un
StatementError) y, sin manejo, se propaga como un 500. `get_session` hace un
warm-up con reintentos para absorberlo. Aquí se valida esa lógica sin tocar AWS.
"""

import pytest
from sqlalchemy.exc import StatementError

from shared import users_db


def _resuming_error():
    """StatementError equivalente al que levanta el Data API al despertar."""
    orig = Exception(
        "An error occurred (DatabaseResumingException) when calling the "
        "BeginTransaction operation: The Aurora DB instance is resuming after "
        "being auto-paused. Please wait a few seconds and try again."
    )
    return StatementError("BeginTransaction", None, None, orig)


class _FakeSession:
    """Sesión mínima que falla `fails` veces con 'resuming' y luego responde."""

    def __init__(self, fails, error=None):
        self.fails = fails
        self.error = error or _resuming_error
        self.calls = 0
        self.rollbacks = 0

    def execute(self, *_a, **_k):
        self.calls += 1
        if self.calls <= self.fails:
            raise self.error()
        return "ok"

    def rollback(self):
        self.rollbacks += 1


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch):
    """Evita esperas reales entre reintentos."""
    monkeypatch.setattr(users_db, "_RESUME_BACKOFF_S", 0)


class TestIsResumingError:
    def test_detecta_por_orig(self):
        assert users_db._is_resuming_error(_resuming_error())

    def test_detecta_por_causa_encadenada(self):
        try:
            raise RuntimeError("wrapper") from _resuming_error()
        except RuntimeError as exc:
            assert users_db._is_resuming_error(exc)

    def test_otro_error_no_es_resuming(self):
        otro = StatementError("stmt", None, None, Exception("syntax error near"))
        assert not users_db._is_resuming_error(otro)


class TestWaitUntilAwake:
    def test_reintenta_y_luego_responde(self):
        s = _FakeSession(fails=2)
        users_db._wait_until_awake(s)
        # 2 fallos + 1 éxito; rollback tras cada fallo reintentado.
        assert s.calls == 3
        assert s.rollbacks == 2

    def test_db_ya_despierta_no_reintenta(self):
        s = _FakeSession(fails=0)
        users_db._wait_until_awake(s)
        assert s.calls == 1
        assert s.rollbacks == 0

    def test_error_no_resuming_se_propaga_sin_reintentar(self):
        s = _FakeSession(fails=99, error=lambda: StatementError(
            "stmt", None, None, Exception("syntax error")))
        with pytest.raises(StatementError):
            users_db._wait_until_awake(s)
        assert s.calls == 1

    def test_agota_reintentos_y_propaga(self, monkeypatch):
        monkeypatch.setattr(users_db, "_RESUME_RETRIES", 3)
        s = _FakeSession(fails=99)  # nunca despierta
        with pytest.raises(StatementError):
            users_db._wait_until_awake(s)
        assert s.calls == 3
