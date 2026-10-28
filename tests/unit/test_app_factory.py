import pytest
from sqlalchemy.engine import make_url

from app import _database_url, create_app

ROUTES = {
    "/api/v1/connexion/signup",
    "/api/v1/token/create",
    "/api/v1/token/revoke",
    "/api/v1/decks",
    "/api/v1/deck/<int:deck_id>",
    "/api/v1/deck/<int:deck_id>/cards",
    "/api/v1/card/<int:card_id>",
}


def test_factory_registers_the_expected_routes_and_no_refresh():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite://"})
    rules = {rule.rule for rule in app.url_map.iter_rules() if rule.rule.startswith("/api")}
    assert rules == ROUTES


def test_config_overrides_defaults():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite://", "TESTING": True})
    assert app.config["TESTING"] is True
    assert str(app.config["SQLALCHEMY_DATABASE_URI"]) == "sqlite://"


def test_connections_are_pre_pinged():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite://"})
    assert app.config["SQLALCHEMY_ENGINE_OPTIONS"]["pool_pre_ping"] is True


def test_each_call_builds_an_independent_app():
    assert create_app({"SQLALCHEMY_DATABASE_URI": "sqlite://"}) is not create_app(
        {"SQLALCHEMY_DATABASE_URI": "sqlite://"}
    )


def test_database_url_is_read_from_the_compose_variable_names(monkeypatch):
    for name, value in {
        "POSTGRES_HOST": "postgres",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DATABASE": "kyl",
        "POSTGRES_USERNAME": "kyl_user",
        "POSTGRES_PASSWORD": "p@ss/word:1",  # special characters must be escaped, not break the URL
    }.items():
        monkeypatch.setenv(name, value)
    url = make_url(_database_url().render_as_string(hide_password=False))
    assert url.drivername == "postgresql+psycopg2"
    assert (url.host, url.port, url.database, url.username) == ("postgres", 5432, "kyl", "kyl_user")
    assert url.password == "p@ss/word:1"


def test_database_url_without_port(monkeypatch):
    monkeypatch.delenv("POSTGRES_PORT", raising=False)
    assert _database_url().port is None
