"""Every deck/card route is protected. @require_token itself is tested in test_auth.py."""

from datetime import timedelta

import pytest

from tests.conftest import bearer

PROTECTED = [
    ("get", "/api/v1/decks"),
    ("post", "/api/v1/decks"),
    ("patch", "/api/v1/deck/1"),
    ("delete", "/api/v1/deck/1"),
    ("get", "/api/v1/deck/1/cards"),
    ("post", "/api/v1/deck/1/cards"),
    ("get", "/api/v1/card/1"),
    ("patch", "/api/v1/card/1"),
    ("delete", "/api/v1/card/1"),
]


def call(client, method, path, headers=None):
    kwargs = {"headers": headers or {}}
    if method in ("post", "patch"):
        kwargs["json"] = {}
    return getattr(client, method)(path, **kwargs)


@pytest.fixture
def user(make_account):
    return make_account()


@pytest.mark.parametrize("method, path", PROTECTED)
def test_anonymous_request_is_rejected(client, method, path):
    response = call(client, method, path)
    assert response.status_code == 401
    assert response.get_json()["error"] == "MissingToken"
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("method, path", PROTECTED)
def test_unknown_token_is_rejected(client, method, path):
    response = call(client, method, path, bearer("never-issued"))
    assert response.status_code == 401
    assert response.get_json()["error"] == "InvalidToken"


@pytest.mark.parametrize("method, path", PROTECTED)
def test_expired_token_is_rejected(client, user, make_token, method, path):
    key = make_token(user["email"], expires_in=timedelta(seconds=-1))
    assert call(client, method, path, bearer(key)).get_json()["error"] == "InvalidToken"


@pytest.mark.parametrize("method, path", PROTECTED)
def test_revoked_token_is_rejected(client, user, make_token, method, path):
    key = make_token(user["email"], revoked=True)
    assert call(client, method, path, bearer(key)).get_json()["error"] == "InvalidToken"


def test_a_revoked_token_cannot_read_decks_any_more(client, user, make_token, make_deck):
    make_deck(user["email"], name="Maths")
    key = make_token(user["email"])
    assert client.get("/api/v1/decks", headers=bearer(key)).status_code == 200
    client.post("/api/v1/token/revoke", headers=bearer(key))
    assert client.get("/api/v1/decks", headers=bearer(key)).status_code == 401
