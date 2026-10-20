"""@require_token, tested on a throw-away route so it does not depend on any real endpoint."""

from datetime import timedelta

import pytest
from flask import g, jsonify

from app import create_app
from auth import require_token
from database import db
from models import Account
from services.token import hash_token
from tests.conftest import bearer

PATH = "/_protected"


@pytest.fixture
def calls():
    return []


@pytest.fixture
def protected_client(app, calls):
    """A second app instance (same DB) exposing one @require_token route."""
    protected_app = create_app(
        {"TESTING": True, "SQLALCHEMY_DATABASE_URI": app.config["SQLALCHEMY_DATABASE_URI"]}
    )

    @protected_app.get(PATH)
    @require_token
    def protected():
        calls.append(1)
        return jsonify(email=g.account_email, token_hash=g.token.token_hash)

    return protected_app.test_client()


@pytest.fixture
def user(make_account):
    return make_account()


class TestAccepted:
    def test_valid_token_reaches_the_view(self, protected_client, user, make_token, calls):
        key = make_token(user["email"])
        response = protected_client.get(PATH, headers=bearer(key))
        assert response.status_code == 200
        assert calls == [1]

    def test_view_receives_the_account_and_the_token(self, protected_client, user, make_token):
        key = make_token(user["email"])
        body = protected_client.get(PATH, headers=bearer(key)).get_json()
        assert body == {"email": user["email"], "token_hash": hash_token(key)}

    def test_token_identifies_its_own_account_and_no_other(self, protected_client, make_account, make_token):
        make_account(email="a@example.com")
        make_account(email="b@example.com")
        key_a, key_b = make_token("a@example.com"), make_token("b@example.com")
        assert protected_client.get(PATH, headers=bearer(key_a)).get_json()["email"] == "a@example.com"
        assert protected_client.get(PATH, headers=bearer(key_b)).get_json()["email"] == "b@example.com"

    @pytest.mark.parametrize("scheme", ["Bearer", "bearer", "BEARER"])
    def test_scheme_is_case_insensitive(self, protected_client, user, make_token, scheme):
        key = make_token(user["email"])
        response = protected_client.get(PATH, headers={"Authorization": f"{scheme} {key}"})
        assert response.status_code == 200

    def test_token_about_to_expire_is_still_valid(self, protected_client, user, make_token):
        key = make_token(user["email"], expires_in=timedelta(seconds=30))
        assert protected_client.get(PATH, headers=bearer(key)).status_code == 200

    def test_decorator_keeps_the_view_name(self):
        @require_token
        def my_view():
            pass

        assert my_view.__name__ == "my_view"


class TestRefused:
    @pytest.fixture(autouse=True)
    def _token(self, user, make_token):
        self.key = make_token(user["email"])

    def assert_refused(self, response, error, calls):
        assert response.status_code == 401
        assert response.get_json()["error"] == error
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert calls == [], "the view must not run when authentication fails"

    def test_no_authorization_header(self, protected_client, calls):
        self.assert_refused(protected_client.get(PATH), "MissingToken", calls)

    @pytest.mark.parametrize("header", ["", "Bearer", "Bearer ", "Bearer    "])
    def test_header_without_a_token(self, protected_client, calls, header):
        response = protected_client.get(PATH, headers={"Authorization": header})
        self.assert_refused(response, "MissingToken", calls)

    @pytest.mark.parametrize("scheme", ["Basic", "Token", "Digest", "Bearer:"])
    def test_other_authorization_schemes(self, protected_client, calls, scheme):
        response = protected_client.get(PATH, headers={"Authorization": f"{scheme} {self.key}"})
        self.assert_refused(response, "MissingToken", calls)

    def test_raw_token_without_a_scheme(self, protected_client, calls):
        response = protected_client.get(PATH, headers={"Authorization": self.key})
        self.assert_refused(response, "MissingToken", calls)

    def test_token_in_the_query_string_is_ignored(self, protected_client, calls):
        self.assert_refused(protected_client.get(f"{PATH}?token={self.key}"), "MissingToken", calls)

    def test_unknown_token(self, protected_client, calls):
        self.assert_refused(
            protected_client.get(PATH, headers=bearer("never-issued")), "InvalidToken", calls
        )

    def test_tampered_token(self, protected_client, calls):
        tampered = self.key[:-1] + ("A" if self.key[-1] != "A" else "B")
        self.assert_refused(protected_client.get(PATH, headers=bearer(tampered)), "InvalidToken", calls)

    def test_truncated_token(self, protected_client, calls):
        self.assert_refused(protected_client.get(PATH, headers=bearer(self.key[:-5])), "InvalidToken", calls)

    def test_the_stored_hash_is_not_a_credential(self, protected_client, calls):
        """A leaked database must not let anyone log in."""
        response = protected_client.get(PATH, headers=bearer(hash_token(self.key)))
        self.assert_refused(response, "InvalidToken", calls)

    def test_expired_token(self, protected_client, user, make_token, calls):
        expired = make_token(user["email"], expires_in=timedelta(seconds=-1))
        self.assert_refused(protected_client.get(PATH, headers=bearer(expired)), "InvalidToken", calls)

    def test_long_expired_token(self, protected_client, user, make_token, calls):
        expired = make_token(user["email"], expires_in=timedelta(days=-400))
        self.assert_refused(protected_client.get(PATH, headers=bearer(expired)), "InvalidToken", calls)

    def test_revoked_token(self, protected_client, user, make_token, calls):
        revoked = make_token(user["email"], revoked=True)
        self.assert_refused(protected_client.get(PATH, headers=bearer(revoked)), "InvalidToken", calls)

    def test_revoked_and_expired_token(self, protected_client, user, make_token, calls):
        key = make_token(user["email"], expires_in=timedelta(days=-1), revoked=True)
        self.assert_refused(protected_client.get(PATH, headers=bearer(key)), "InvalidToken", calls)

    def test_token_of_a_deleted_account(self, protected_client, app, calls):
        with app.app_context():
            db.session.delete(db.session.get(Account, "user@example.com"))
            db.session.commit()
        self.assert_refused(protected_client.get(PATH, headers=bearer(self.key)), "InvalidToken", calls)

    def test_error_body_has_a_code_and_a_message_and_nothing_else(self, protected_client):
        body = protected_client.get(PATH, headers=bearer("never-issued")).get_json()
        assert set(body) == {"error", "message"}

    def test_the_failure_reason_is_not_revealed(self, protected_client, user, make_token):
        """Unknown, expired and revoked tokens look exactly the same from outside."""
        expired = make_token(user["email"], expires_in=timedelta(seconds=-1))
        revoked = make_token(user["email"], revoked=True)
        responses = [
            protected_client.get(PATH, headers=bearer(k)).get_data()
            for k in ("never-issued", expired, revoked)
        ]
        assert len(set(responses)) == 1
