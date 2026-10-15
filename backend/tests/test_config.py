import os

import pytest

from src.config import (
    database_uri,
    env_bool,
    env_list,
    optional_env,
    optional_int_env,
    require_env,
    require_int_env,
)

VAR = "ABACUS_TEST_VAR"


def test_require_env_missing_raises(monkeypatch):
    monkeypatch.delenv(VAR, raising=False)
    with pytest.raises(RuntimeError, match=VAR):
        require_env(VAR)


def test_require_env_blank_counts_as_missing(monkeypatch):
    monkeypatch.setenv(VAR, "   ")
    with pytest.raises(RuntimeError, match="is not set"):
        require_env(VAR)


def test_require_env_strips_whitespace(monkeypatch):
    monkeypatch.setenv(VAR, "  value  ")
    assert require_env(VAR) == "value"


def test_optional_env_default(monkeypatch):
    monkeypatch.delenv(VAR, raising=False)
    assert optional_env(VAR) is None
    assert optional_env(VAR, "fallback") == "fallback"


def test_require_int_env_rejects_non_int(monkeypatch):
    monkeypatch.setenv(VAR, "abc")
    with pytest.raises(RuntimeError, match="integer"):
        require_int_env(VAR)


def test_optional_int_env(monkeypatch):
    monkeypatch.delenv(VAR, raising=False)
    assert optional_int_env(VAR, 42) == 42
    monkeypatch.setenv(VAR, "7")
    assert optional_int_env(VAR, 42) == 7


@pytest.mark.parametrize(
    "raw, expected",
    [("true", True), ("1", True), ("YES", True), ("on", True), ("false", False), ("0", False), ("", False)],
)
def test_env_bool(monkeypatch, raw, expected):
    monkeypatch.setenv(VAR, raw)
    assert env_bool(VAR, False) is expected


def test_env_bool_default_when_unset(monkeypatch):
    monkeypatch.delenv(VAR, raising=False)
    assert env_bool(VAR, True) is True


def test_env_list_splits_and_strips(monkeypatch):
    monkeypatch.setenv(VAR, " a, b ,,c ")
    assert env_list(VAR) == ["a", "b", "c"]


def test_env_list_default_when_unset(monkeypatch):
    monkeypatch.delenv(VAR, raising=False)
    assert env_list(VAR, ["x"]) == ["x"]
    assert env_list(VAR) == []


def test_database_uri_defaults_port_and_escapes_credentials(monkeypatch):
    monkeypatch.setenv("DB_USER", "api-user")
    monkeypatch.setenv("DB_PASSWORD", "p@ss/w:rd")
    monkeypatch.setenv("DB_HOST", "db")
    monkeypatch.setenv("DB_NAME", "autota")
    monkeypatch.delenv("DB_PORT", raising=False)
    assert database_uri() == "mysql+pymysql://api-user:p%40ss%2Fw%3Ard@db:3306/autota"


def test_database_uri_honours_port(monkeypatch):
    monkeypatch.setenv("DB_USER", "u")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("DB_HOST", "h")
    monkeypatch.setenv("DB_NAME", "n")
    monkeypatch.setenv("DB_PORT", "3307")
    assert database_uri().endswith("@h:3307/n")


def test_create_app_fails_fast_without_jwt_secret(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    from app import create_app

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        create_app()


def test_jwt_secret_comes_from_env(app):
    assert app.config["JWT_SECRET_KEY"] == os.environ["JWT_SECRET_KEY"]


def test_cors_origin_defaults_to_frontend_base_url(app):
    # conftest sets FRONTEND_BASE_URL=http://localhost:3000 and no CORS_ORIGINS.
    response = app.test_client().options(
        "/api/schools/config/divisions",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"
