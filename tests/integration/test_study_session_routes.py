"""
GET /api/v1/sessions, POST /api/v1/session, DELETE /api/v1/session/<id>

Contract:
  - JSON study session: {"session_id", "timestamp", "owner_email", "tolerance_allowed",
    "is_tolerance_forced"}
  - POST body: timestamp (ISO 8601 string), tolerance_allowed, is_tolerance_forced (all required)
    -> {"session": {...}}
  - at most MAX_SESSION_BY_USER sessions per user: the OLDEST one is evicted (with its snapshots)
  - a session of another account is a 404, exactly like an unknown id
  - snapshots are immutable: there is no GET-by-id and no PATCH
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import routes.session as session_routes
from consts import MAX_SESSION_BY_USER
from database import db
from models import SessionCard, SessionDeck, StudySession
from tests.conftest import bearer

SESSIONS = "/api/v1/sessions"
SESSION = "/api/v1/session"
SESSION_FIELDS = {
    "session_id", "timestamp", "owner_email", "tolerance_allowed", "is_tolerance_forced",
}
VALID = {
    "timestamp": "2026-01-01T12:00:00+00:00",
    "tolerance_allowed": True,
    "is_tolerance_forced": False,
}
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def session_url(session_id):
    return f"/api/v1/session/{session_id}"


def stored_sessions(app, email=None):
    with app.app_context():
        query = select(StudySession)
        if email:
            query = query.where(StudySession.owner_email == email)
        return db.session.scalars(query).all()


def stored_session(app, session_id):
    with app.app_context():
        found = db.session.get(StudySession, session_id)
        if found is None:
            return None
        return (found.owner_email, found.tolerance_allowed, found.is_tolerance_forced)


def count_snapshots(app):
    with app.app_context():
        return (
            len(db.session.scalars(select(SessionDeck)).all()),
            len(db.session.scalars(select(SessionCard)).all()),
        )


@pytest.fixture
def user(make_account):
    return make_account()


@pytest.fixture
def other(make_account):
    return make_account(email="other@example.com")


@pytest.fixture
def headers(user, make_token):
    return bearer(make_token(user["email"]))


@pytest.fixture
def small_limit(monkeypatch):
    """Creating MAX_SESSION_BY_USER rows for each test is slow: shrink the limit where it is used."""
    monkeypatch.setattr(session_routes, "MAX_SESSION_BY_USER", 3)
    return 3


class TestList:
    def test_returns_only_my_sessions(self, client, user, other, headers, make_study_session):
        mine = make_study_session(user["email"])
        make_study_session(other["email"])
        response = client.get(SESSIONS, headers=headers)
        assert response.status_code == 200
        assert [s["session_id"] for s in response.get_json()] == [mine]

    def test_empty_list_when_no_session(self, client, headers):
        response = client.get(SESSIONS, headers=headers)
        assert response.status_code == 200
        assert response.get_json() == []

    def test_session_shape(self, client, user, headers, make_study_session):
        session_id = make_study_session(
            user["email"], timestamp=T0, tolerance_allowed=False, is_tolerance_forced=True
        )
        (body,) = client.get(SESSIONS, headers=headers).get_json()
        assert set(body) == SESSION_FIELDS
        assert body["session_id"] == session_id
        assert body["owner_email"] == user["email"]
        assert body["tolerance_allowed"] is False
        assert body["is_tolerance_forced"] is True
        assert datetime.fromisoformat(body["timestamp"]) == T0

    def test_sorted_by_timestamp(self, client, user, headers, make_study_session):
        newest = make_study_session(user["email"], timestamp=T0 + timedelta(days=2))
        oldest = make_study_session(user["email"], timestamp=T0)
        middle = make_study_session(user["email"], timestamp=T0 + timedelta(days=1))
        ids = [s["session_id"] for s in client.get(SESSIONS, headers=headers).get_json()]
        assert ids == [oldest, middle, newest]


class TestCreate:
    def test_returns_201_with_the_new_session(self, client, user, headers):
        response = client.post(SESSION, json=VALID, headers=headers)
        assert response.status_code == 201
        created = response.get_json()["session"]
        assert set(created) == SESSION_FIELDS
        assert created["owner_email"] == user["email"]
        assert created["tolerance_allowed"] is True
        assert created["is_tolerance_forced"] is False
        assert datetime.fromisoformat(created["timestamp"]) == datetime.fromisoformat(
            VALID["timestamp"]
        )

    def test_the_session_is_stored_for_the_caller(self, client, app, user, headers):
        session_id = client.post(SESSION, json=VALID, headers=headers).get_json()["session"][
            "session_id"
        ]
        assert stored_session(app, session_id) == (user["email"], True, False)

    def test_the_client_cannot_choose_the_owner_or_the_id(self, client, user, other, headers):
        body = {**VALID, "owner_email": other["email"], "session_id": 999}
        created = client.post(SESSION, json=body, headers=headers).get_json()["session"]
        assert created["owner_email"] == user["email"]
        assert created["session_id"] != 999

    @pytest.mark.parametrize("tolerance_allowed", [True, False])
    @pytest.mark.parametrize("is_tolerance_forced", [True, False])
    def test_booleans_are_kept_as_sent(
        self, client, headers, tolerance_allowed, is_tolerance_forced
    ):
        body = {
            **VALID,
            "tolerance_allowed": tolerance_allowed,
            "is_tolerance_forced": is_tolerance_forced,
        }
        created = client.post(SESSION, json=body, headers=headers).get_json()["session"]
        assert created["tolerance_allowed"] is tolerance_allowed
        assert created["is_tolerance_forced"] is is_tolerance_forced

    def test_each_creation_gives_a_distinct_id(self, client, headers):
        first = client.post(SESSION, json=VALID, headers=headers).get_json()["session"]
        second = client.post(SESSION, json=VALID, headers=headers).get_json()["session"]
        assert first["session_id"] != second["session_id"]

    @pytest.mark.parametrize("missing", list(VALID))
    def test_missing_field(self, client, app, headers, missing):
        body = {k: v for k, v in VALID.items() if k != missing}
        response = client.post(SESSION, json=body, headers=headers)
        assert response.status_code == 400
        assert response.get_json()["error"] == "InvalidRequest"
        assert response.get_json()["message"].startswith(f"{missing}:")
        assert stored_sessions(app) == []

    @pytest.mark.parametrize(
        "field, value",
        [
            ("timestamp", "yesterday"), ("timestamp", ""), ("timestamp", 123), ("timestamp", None),
            ("tolerance_allowed", "true"), ("tolerance_allowed", 1), ("tolerance_allowed", None),
            ("is_tolerance_forced", "false"), ("is_tolerance_forced", 0),
            ("is_tolerance_forced", None),
        ],
    )
    def test_wrong_type_or_invalid_timestamp(self, client, app, headers, field, value):
        response = client.post(SESSION, json={**VALID, field: value}, headers=headers)
        assert response.status_code == 400
        assert response.get_json()["error"] == "InvalidRequest"
        assert stored_sessions(app) == []

    @pytest.mark.parametrize(
        "kwargs",
        [{"data": "nope", "content_type": "application/json"}, {"json": [1]}, {"json": "t"}, {}],
    )
    def test_body_that_is_not_a_json_object(self, client, headers, kwargs):
        response = client.post(SESSION, headers=headers, **kwargs)
        assert response.status_code == 400
        assert response.get_json()["error"] == "InvalidRequest"

    def test_error_body_has_a_code_and_a_message(self, client, headers):
        body = client.post(SESSION, json={}, headers=headers).get_json()
        assert set(body) == {"error", "message"}


class TestSessionLimit:
    def test_the_real_limit_is_a_positive_number(self):
        assert MAX_SESSION_BY_USER > 0

    def test_last_allowed_session_is_accepted(
        self, client, app, user, headers, make_study_session, small_limit
    ):
        for i in range(small_limit - 1):
            make_study_session(user["email"], timestamp=T0 + timedelta(days=i))
        assert client.post(SESSION, json=VALID, headers=headers).status_code == 201
        assert len(stored_sessions(app, user["email"])) == small_limit

    def test_at_the_limit_the_oldest_session_is_evicted(
        self, client, app, user, headers, make_study_session, small_limit
    ):
        ids = [
            make_study_session(user["email"], timestamp=T0 + timedelta(days=i))
            for i in range(small_limit)
        ]
        # VALID is dated 2026-01-01: older than... nothing here, it is the newest write
        created = client.post(SESSION, json=VALID, headers=headers).get_json()["session"]
        remaining = {s.session_id for s in stored_sessions(app, user["email"])}
        assert len(remaining) == small_limit
        assert ids[0] not in remaining
        assert set(ids[1:]) <= remaining
        assert created["session_id"] in remaining

    def test_the_evicted_session_loses_its_decks_and_cards(
        self, client, app, user, headers, make_study_session, make_session_deck, small_limit
    ):
        oldest = make_study_session(user["email"], timestamp=T0)
        make_session_deck(oldest, cards=[("q", "a", "a")])
        for i in range(1, small_limit):
            make_study_session(user["email"], timestamp=T0 + timedelta(days=i))
        client.post(SESSION, json=VALID, headers=headers)
        assert count_snapshots(app) == (0, 0)

    def test_the_other_sessions_keep_their_snapshots(
        self, client, app, user, headers, make_study_session, make_session_deck, small_limit
    ):
        make_study_session(user["email"], timestamp=T0)
        kept = make_study_session(user["email"], timestamp=T0 + timedelta(days=1))
        make_session_deck(kept, cards=[("q", "a", "a")])
        make_study_session(user["email"], timestamp=T0 + timedelta(days=2))
        client.post(SESSION, json=VALID, headers=headers)
        assert count_snapshots(app) == (1, 1)

    def test_sessions_of_other_users_are_untouched(
        self, client, app, user, other, headers, make_study_session, small_limit
    ):
        for i in range(small_limit):
            make_study_session(other["email"], timestamp=T0 - timedelta(days=i + 1))
            make_study_session(user["email"], timestamp=T0 + timedelta(days=i))
        client.post(SESSION, json=VALID, headers=headers)
        assert len(stored_sessions(app, other["email"])) == small_limit

    def test_the_limit_is_per_user(
        self, client, user, other, headers, make_study_session, small_limit
    ):
        for i in range(small_limit):
            make_study_session(other["email"], timestamp=T0 + timedelta(days=i))
        assert client.post(SESSION, json=VALID, headers=headers).status_code == 201

    def test_a_failed_creation_does_not_evict_anything(
        self, client, app, user, headers, make_study_session, small_limit
    ):
        for i in range(small_limit):
            make_study_session(user["email"], timestamp=T0 + timedelta(days=i))
        assert client.post(SESSION, json={}, headers=headers).status_code == 400
        assert len(stored_sessions(app, user["email"])) == small_limit


class TestDelete:
    def test_deletes_the_session(self, client, app, user, headers, make_study_session):
        session_id = make_study_session(user["email"])
        response = client.delete(session_url(session_id), headers=headers)
        assert response.status_code == 200
        assert response.get_json() == {"message": "Session deleted successfully"}
        assert stored_session(app, session_id) is None

    def test_its_decks_and_cards_are_deleted_too(
        self, client, app, user, headers, make_study_session, make_session_deck
    ):
        session_id = make_study_session(user["email"])
        make_session_deck(session_id, name="A", cards=[("q1", "a", "a"), ("q2", "a", "b")])
        make_session_deck(session_id, name="B", cards=[("q3", "a", "a")])
        assert count_snapshots(app) == (2, 3)
        client.delete(session_url(session_id), headers=headers)
        assert count_snapshots(app) == (0, 0)

    def test_other_sessions_and_their_snapshots_are_intact(
        self, client, app, user, other, headers, make_study_session, make_session_deck
    ):
        target = make_study_session(user["email"])
        make_session_deck(target, cards=[("q", "a", "a")])
        mine = make_study_session(user["email"])
        make_session_deck(mine, cards=[("q", "a", "a")])
        theirs = make_study_session(other["email"])
        make_session_deck(theirs, cards=[("q", "a", "a")])
        client.delete(session_url(target), headers=headers)
        assert stored_session(app, mine) is not None
        assert stored_session(app, theirs) is not None
        assert count_snapshots(app) == (2, 2)

    def test_session_of_another_user_is_404_and_kept(
        self, client, app, other, headers, make_study_session
    ):
        session_id = make_study_session(other["email"])
        response = client.delete(session_url(session_id), headers=headers)
        assert response.status_code == 404
        assert response.get_json()["error"] == "SessionNotFound"
        assert stored_session(app, session_id) is not None

    def test_unknown_session(self, client, headers):
        response = client.delete(session_url(99999), headers=headers)
        assert response.status_code == 404
        assert response.get_json()["error"] == "SessionNotFound"

    def test_other_users_session_and_unknown_session_are_indistinguishable(
        self, client, other, headers, make_study_session
    ):
        theirs = client.delete(session_url(make_study_session(other["email"])), headers=headers)
        unknown = client.delete(session_url(99999), headers=headers)
        assert theirs.status_code == unknown.status_code
        assert theirs.get_data() == unknown.get_data()

    def test_deleting_twice(self, client, user, headers, make_study_session):
        session_id = make_study_session(user["email"])
        assert client.delete(session_url(session_id), headers=headers).status_code == 200
        assert client.delete(session_url(session_id), headers=headers).status_code == 404

    def test_non_integer_id_is_404(self, client, headers):
        assert client.delete("/api/v1/session/abc", headers=headers).status_code == 404


class TestMethodsAndPaths:
    def test_sessions_collection_allows_only_get(self, client, headers):
        assert client.post(SESSIONS, json=VALID, headers=headers).status_code == 405
        assert client.put(SESSIONS, json={}, headers=headers).status_code == 405
        assert client.patch(SESSIONS, json={}, headers=headers).status_code == 405
        assert client.delete(SESSIONS, headers=headers).status_code == 405

    def test_session_creation_path_allows_only_post(self, client, headers):
        assert client.get(SESSION, headers=headers).status_code == 405
        assert client.put(SESSION, json={}, headers=headers).status_code == 405
        assert client.delete(SESSION, headers=headers).status_code == 405

    def test_single_session_allows_only_delete(self, client, user, headers, make_study_session):
        session_id = make_study_session(user["email"])
        assert client.get(session_url(session_id), headers=headers).status_code == 405
        assert client.put(session_url(session_id), json={}, headers=headers).status_code == 405
        assert client.patch(session_url(session_id), json={}, headers=headers).status_code == 405
        assert client.post(session_url(session_id), json={}, headers=headers).status_code == 405
