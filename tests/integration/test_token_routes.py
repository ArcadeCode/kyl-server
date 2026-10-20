"""POST /api/v1/token/create (login) and POST /api/v1/token/revoke (logout)"""

from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest
from sqlalchemy import select

import routes.token as token_routes
from database import db
from models import Account, Token
from services.token import hash_token
from tests.conftest import bearer

CREATE = "/api/v1/token/create"
REVOKE = "/api/v1/token/revoke"


def login(client, email="user@example.com", password="abc12"):
    return client.post(CREATE, json={"email": email, "password": password})


def stored_tokens(app, email=None):
    with app.app_context():
        query = select(Token)
        if email:
            query = query.where(Token.account_email == email)
        return db.session.scalars(query).all()


def stored_password_hash(app, email="user@example.com"):
    with app.app_context():
        return db.session.get(Account, email).password


@pytest.fixture
def user(make_account):
    return make_account()


class TestLogin:
    def test_returns_201_with_a_token_and_its_expiry(self, client, user):
        response = login(client)
        assert response.status_code == 201
        body = response.get_json()
        assert set(body) == {"token", "expires_at"}
        assert len(body["token"]) >= 43

    def test_token_expires_in_30_days(self, client, user):
        expires_at = datetime.fromisoformat(login(client).get_json()["expires_at"])
        expected = datetime.now(timezone.utc) + timedelta(days=30)
        assert expires_at.tzinfo is not None
        assert abs(expires_at - expected) < timedelta(minutes=1)

    def test_response_must_not_be_cached(self, client, user):
        assert login(client).headers["Cache-Control"] == "no-store"

    def test_only_the_hash_of_the_token_is_stored(self, client, app, user):
        key = login(client).get_json()["token"]
        (stored,) = stored_tokens(app)
        assert stored.token_hash == hash_token(key)
        assert key not in (stored.token_hash, stored.account_email)

    def test_stored_token_is_linked_to_the_account_and_valid(self, client, app, user):
        login(client)
        (stored,) = stored_tokens(app)
        assert stored.account_email == "user@example.com"
        assert stored.revoked_at is None
        assert stored.expires_at > datetime.now(timezone.utc)

    def test_the_returned_token_works_on_a_protected_route(self, client, user):
        key = login(client).get_json()["token"]
        assert client.post(REVOKE, headers=bearer(key)).status_code == 200

    def test_email_is_trimmed_and_case_insensitive(self, client, user):
        assert login(client, email="  USER@Example.com ").status_code == 201

    def test_each_login_creates_a_distinct_token_one_per_device(self, client, app, user):
        first = login(client).get_json()["token"]
        second = login(client).get_json()["token"]
        assert first != second
        assert len(stored_tokens(app, "user@example.com")) == 2
        assert client.post(REVOKE, headers=bearer(first)).status_code == 200
        assert client.post(REVOKE, headers=bearer(second)).status_code == 200

    def test_password_hash_gets_a_fresh_salt_and_still_works(self, client, app, user):
        before = stored_password_hash(app)
        login(client)
        after = stored_password_hash(app)
        assert after != before
        assert login(client).status_code == 201

    def test_tokens_of_other_accounts_are_untouched(self, client, app, user, make_account):
        make_account(email="other@example.com")
        login(client)
        assert stored_tokens(app, "other@example.com") == []


class TestLoginFailures:
    def test_wrong_password(self, client, user):
        response = login(client, password="wrong1")
        assert response.status_code == 401
        assert response.get_json()["error"] == "InvalidCredentials"

    def test_unknown_email(self, client, user):
        response = login(client, email="ghost@example.com")
        assert response.status_code == 401
        assert response.get_json()["error"] == "InvalidCredentials"

    def test_unknown_email_and_wrong_password_are_indistinguishable(self, client, user):
        wrong_password = login(client, password="wrong1")
        unknown_email = login(client, email="ghost@example.com", password="wrong1")
        assert wrong_password.status_code == unknown_email.status_code
        assert wrong_password.get_json() == unknown_email.get_json()
        assert wrong_password.get_data() == unknown_email.get_data()

    def test_unknown_email_still_costs_a_bcrypt_verification(self, client, user):
        with mock.patch.object(token_routes, "fake_verify") as fake, \
             mock.patch.object(token_routes, "compare_password") as real:
            login(client, email="ghost@example.com")
        fake.assert_called_once_with("abc12")
        real.assert_not_called()

    def test_known_email_does_not_use_the_fake_verification(self, client, user):
        with mock.patch.object(token_routes, "fake_verify") as fake:
            login(client, password="wrong1")
        fake.assert_not_called()

    def test_failure_creates_no_token_and_keeps_the_hash(self, client, app, user):
        before = stored_password_hash(app)
        login(client, password="wrong1")
        login(client, email="ghost@example.com")
        assert stored_tokens(app) == []
        assert stored_password_hash(app) == before

    def test_password_is_case_sensitive(self, client, user):
        assert login(client, password="ABC12").status_code == 401

    def test_password_longer_than_72_bytes_is_a_401_not_a_crash(self, client, user):
        assert login(client, password="a1" * 60).status_code == 401
        assert login(client, email="ghost@example.com", password="é" * 80).status_code == 401

    @pytest.mark.parametrize("missing", ["email", "password"])
    def test_missing_field(self, client, user, missing):
        body = {k: v for k, v in {"email": "user@example.com", "password": "abc12"}.items() if k != missing}
        response = client.post(CREATE, json=body)
        assert response.status_code == 400
        assert response.get_json()["error"] == "InvalidRequest"

    @pytest.mark.parametrize("value", [123, None, ["a"], {"a": 1}])
    def test_wrong_type(self, client, user, value):
        assert client.post(CREATE, json={"email": value, "password": "abc12"}).status_code == 400
        assert client.post(CREATE, json={"email": "user@example.com", "password": value}).status_code == 400

    @pytest.mark.parametrize(
        "kwargs",
        [{"data": "nope", "content_type": "application/json"}, {"json": [1, 2]}, {}],
    )
    def test_body_that_is_not_a_json_object(self, client, kwargs):
        assert client.post(CREATE, **kwargs).status_code == 400

    def test_only_post_is_allowed(self, client):
        assert client.get(CREATE).status_code == 405
        assert client.put(CREATE, json={}).status_code == 405


class TestNoRefresh:
    """Tokens have a fixed 30 day lifetime: logging in again is the only way to get a new one."""

    @pytest.mark.parametrize("path", ["/api/v1/token/refresh", "/api/v1/token/renew"])
    def test_there_is_no_refresh_route(self, client, user, path):
        key = login(client).get_json()["token"]
        assert client.post(path, headers=bearer(key)).status_code == 404


class TestRevoke:
    def test_revokes_the_token_used_for_the_request(self, client, app, user, make_token):
        key = make_token(user["email"])
        response = client.post(REVOKE, headers=bearer(key))
        assert response.status_code == 200
        assert response.get_json() == {"status": "ok"}
        (stored,) = stored_tokens(app)
        assert stored.revoked_at is not None
        assert abs(datetime.now(timezone.utc) - stored.revoked_at) < timedelta(minutes=1)

    def test_the_token_is_unusable_afterwards(self, client, user, make_token):
        key = make_token(user["email"])
        client.post(REVOKE, headers=bearer(key))
        again = client.post(REVOKE, headers=bearer(key))
        assert again.status_code == 401
        assert again.get_json()["error"] == "InvalidToken"

    def test_other_devices_of_the_same_account_stay_logged_in(self, client, app, user, make_token):
        phone, laptop = make_token(user["email"]), make_token(user["email"])
        client.post(REVOKE, headers=bearer(phone))
        assert client.post(REVOKE, headers=bearer(laptop)).status_code == 200

    def test_tokens_of_other_accounts_are_untouched(self, client, app, user, make_account, make_token):
        make_account(email="other@example.com")
        mine = make_token(user["email"])
        theirs = make_token("other@example.com")
        client.post(REVOKE, headers=bearer(mine))
        (other,) = stored_tokens(app, "other@example.com")
        assert other.revoked_at is None
        assert client.post(REVOKE, headers=bearer(theirs)).status_code == 200

    def test_login_after_logout_gives_a_new_working_token(self, client, user):
        old = login(client).get_json()["token"]
        client.post(REVOKE, headers=bearer(old))
        new = login(client).get_json()["token"]
        assert new != old
        assert client.post(REVOKE, headers=bearer(new)).status_code == 200

    def test_requires_authentication(self, client, user):
        assert client.post(REVOKE).status_code == 401

    def test_only_post_is_allowed(self, client):
        assert client.get(REVOKE).status_code == 405
