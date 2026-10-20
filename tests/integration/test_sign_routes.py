"""POST /api/v1/connexion/signup"""

import bcrypt
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database import db
from models import Account

URL = "/api/v1/connexion/signup"
VALID = {"email": "user@example.com", "password": "abc12", "name": "User"}


def signup(client, **overrides):
    return client.post(URL, json={**VALID, **overrides})


def all_accounts(app):
    with app.app_context():
        return db.session.scalars(select(Account)).all()


class TestSuccess:
    def test_returns_201_with_email_and_name_only(self, client):
        response = signup(client)
        assert response.status_code == 201
        assert response.get_json() == {"email": "user@example.com", "name": "User"}

    def test_response_never_leaks_the_password_or_its_hash(self, client):
        body = signup(client).get_data(as_text=True)
        assert "abc12" not in body
        assert "$2b$" not in body
        assert "password" not in body

    def test_password_is_stored_as_a_bcrypt_hash(self, client, app):
        signup(client)
        (account,) = all_accounts(app)
        assert account.password != "abc12"
        assert account.password.startswith("$2b$")
        assert bcrypt.checkpw(b"abc12", account.password.encode())

    def test_email_is_trimmed_and_lowercased(self, client, app):
        response = signup(client, email="  User@Example.COM ")
        assert response.get_json()["email"] == "user@example.com"
        assert [a.email for a in all_accounts(app)] == ["user@example.com"]

    def test_name_is_trimmed(self, client):
        assert signup(client, name="  Alice  ").get_json()["name"] == "Alice"

    def test_longest_accepted_values(self, client):
        long_local = "a" * (254 - len("@b.fr"))
        assert signup(client, email=f"{long_local}@b.fr").status_code == 201
        assert signup(client, email="x@y.fr", name="n" * 100).status_code == 201
        assert signup(client, email="z@y.fr", password="a1" * 36).status_code == 201


class TestDuplicate:
    def test_same_email_returns_409(self, client):
        signup(client)
        response = signup(client, name="Other")
        assert response.status_code == 409
        assert response.get_json()["error"] == "EmailAlreadyUsed"

    def test_email_case_does_not_bypass_uniqueness(self, client, app):
        signup(client)
        assert signup(client, email="USER@example.com").status_code == 409
        assert len(all_accounts(app)) == 1

    def test_duplicate_does_not_overwrite_the_existing_account(self, client, app):
        signup(client)
        signup(client, password="zzz99", name="Hacker")
        (account,) = all_accounts(app)
        assert account.name == "User"
        assert bcrypt.checkpw(b"abc12", account.password.encode())

    def test_race_condition_is_answered_409_and_session_stays_usable(self, client, app, monkeypatch):
        """Two signups with the same email at the same time: the uniqueness check passes
        for both, the DB constraint catches the second one."""
        signup(client)
        with monkeypatch.context() as patch:
            # make the "already exists?" pre-check blind
            patch.setattr(db.session, "get", lambda *args, **kwargs: None)
            response = signup(client, name="Racer")
        assert response.status_code == 409
        assert response.get_json()["error"] == "EmailAlreadyUsed"
        assert signup(client, email="next@example.com").status_code == 201


class TestValidation:
    @pytest.mark.parametrize(
        "email",
        ["", "plain", "a@b", "@b.fr", "a b@c.fr", "a@@b.fr", "a" * 250 + "@b.fr"],
    )
    def test_invalid_email(self, client, email):
        response = signup(client, email=email)
        assert response.status_code == 400
        assert response.get_json()["error"] == "InvalidEmail"

    @pytest.mark.parametrize(
        "password",
        ["", "ab12", "abcdef", "123456", "abc 12", "abç12", "abc-12", "a1" * 36 + "b"],
    )
    def test_invalid_password(self, client, password):
        response = signup(client, password=password)
        assert response.status_code == 400
        assert response.get_json()["error"] == "InvalidPassword"

    @pytest.mark.parametrize("name", ["", "   ", "n" * 101])
    def test_invalid_name(self, client, name):
        response = signup(client, name=name)
        assert response.status_code == 400
        assert response.get_json()["error"] == "InvalidName"

    @pytest.mark.parametrize("missing", ["email", "password", "name"])
    def test_missing_field(self, client, missing):
        body = {k: v for k, v in VALID.items() if k != missing}
        response = client.post(URL, json=body)
        assert response.status_code == 400
        assert response.get_json()["error"] == "InvalidRequest"

    @pytest.mark.parametrize("field", ["email", "password", "name"])
    @pytest.mark.parametrize("value", [123, None, ["a"], {"a": 1}, True])
    def test_wrong_type(self, client, field, value):
        response = signup(client, **{field: value})
        assert response.status_code == 400
        assert response.get_json()["error"] == "InvalidRequest"

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"data": "not json", "content_type": "application/json"},
            {"data": "email=a&password=b", "content_type": "application/x-www-form-urlencoded"},
            {"json": ["email", "password"]},
            {"json": "text"},
            {},
        ],
    )
    def test_body_that_is_not_a_json_object(self, client, kwargs):
        response = client.post(URL, **kwargs)
        assert response.status_code == 400
        assert response.get_json()["error"] == "InvalidRequest"

    def test_nothing_is_stored_when_validation_fails(self, client, app):
        signup(client, password="short")
        signup(client, email="nope")
        assert all_accounts(app) == []

    def test_error_body_has_a_code_and_a_message(self, client):
        body = signup(client, email="nope").get_json()
        assert set(body) == {"error", "message"}


def test_only_post_is_allowed(client):
    assert client.get(URL).status_code == 405
    assert client.put(URL, json=VALID).status_code == 405
    assert client.delete(URL).status_code == 405
