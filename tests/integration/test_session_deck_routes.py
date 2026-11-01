"""
GET/POST /api/v1/session/<id>/decks, DELETE /api/v1/session/deck/<id>

Contract:
  - JSON session deck: {"session_deck_id", "name", "description", "study_session_id"}
  - POST body: name (required, trimmed), description (optional) -> {"session_deck": {...}}
  - at most MAX_DECK_BY_SESSION decks per study session
  - several session decks may share a name (unlike Deck)
  - anything under a session of another account is a 404, exactly like an unknown id
"""

import pytest
from sqlalchemy import select

from consts import MAX_DECK_BY_SESSION
from database import db
from models import SessionCard, SessionDeck, StudySession
from tests.conftest import bearer

SESSION_DECK_FIELDS = {"session_deck_id", "name", "description", "study_session_id"}


def decks_url(session_id):
    return f"/api/v1/session/{session_id}/decks"


def deck_url(session_deck_id):
    return f"/api/v1/session/deck/{session_deck_id}"


def stored_decks(app, session_id=None):
    with app.app_context():
        query = select(SessionDeck)
        if session_id is not None:
            query = query.where(SessionDeck.study_session_id == session_id)
        return [
            (d.name, d.description, d.study_session_id) for d in db.session.scalars(query).all()
        ]


def stored_deck(app, session_deck_id):
    with app.app_context():
        deck = db.session.get(SessionDeck, session_deck_id)
        return None if deck is None else (deck.name, deck.description, deck.study_session_id)


def stored_card_count(app):
    with app.app_context():
        return len(db.session.scalars(select(SessionCard)).all())


def session_exists(app, session_id):
    with app.app_context():
        return db.session.get(StudySession, session_id) is not None


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
def session_id(user, make_study_session):
    return make_study_session(user["email"])


@pytest.fixture
def foreign_session_id(other, make_study_session):
    return make_study_session(other["email"])


class TestList:
    def test_returns_the_decks_of_this_session(self, client, session_id, headers, make_session_deck):
        make_session_deck(session_id, name="Maths")
        make_session_deck(session_id, name="Physics")
        response = client.get(decks_url(session_id), headers=headers)
        assert response.status_code == 200
        assert sorted(d["name"] for d in response.get_json()) == ["Maths", "Physics"]

    def test_deck_shape(self, client, session_id, headers, make_session_deck):
        deck_id = make_session_deck(session_id, name="Maths", description="Chap. 1")
        (body,) = client.get(decks_url(session_id), headers=headers).get_json()
        assert set(body) == SESSION_DECK_FIELDS
        assert body == {
            "session_deck_id": deck_id,
            "name": "Maths",
            "description": "Chap. 1",
            "study_session_id": session_id,
        }

    def test_empty_list(self, client, session_id, headers):
        response = client.get(decks_url(session_id), headers=headers)
        assert response.status_code == 200
        assert response.get_json() == []

    def test_sessions_of_the_same_user_are_isolated(
        self, client, user, session_id, headers, make_study_session, make_session_deck
    ):
        make_session_deck(session_id, name="Mine")
        elsewhere = make_study_session(user["email"])
        make_session_deck(elsewhere, name="Elsewhere")
        names = [d["name"] for d in client.get(decks_url(session_id), headers=headers).get_json()]
        assert names == ["Mine"]

    def test_session_of_another_user_is_404_without_leak(
        self, client, foreign_session_id, headers, make_session_deck
    ):
        make_session_deck(foreign_session_id, name="secret")
        response = client.get(decks_url(foreign_session_id), headers=headers)
        assert response.status_code == 404
        assert response.get_json()["error"] == "SessionNotFound"
        assert b"secret" not in response.get_data()

    def test_unknown_session(self, client, headers):
        response = client.get(decks_url(99999), headers=headers)
        assert response.status_code == 404
        assert response.get_json()["error"] == "SessionNotFound"

    def test_other_users_session_and_unknown_session_are_indistinguishable(
        self, client, foreign_session_id, headers
    ):
        theirs = client.get(decks_url(foreign_session_id), headers=headers)
        unknown = client.get(decks_url(99999), headers=headers)
        assert theirs.status_code == unknown.status_code
        assert theirs.get_data() == unknown.get_data()


class TestCreate:
    def test_returns_201_with_the_new_deck(self, client, session_id, headers):
        response = client.post(
            decks_url(session_id), json={"name": "Maths", "description": "Chap. 1"}, headers=headers
        )
        assert response.status_code == 201
        deck = response.get_json()["session_deck"]
        assert set(deck) == SESSION_DECK_FIELDS
        assert (deck["name"], deck["description"], deck["study_session_id"]) == (
            "Maths", "Chap. 1", session_id,
        )

    def test_the_deck_is_stored_in_this_session(self, client, app, session_id, headers):
        client.post(decks_url(session_id), json={"name": "Maths"}, headers=headers)
        assert stored_decks(app) == [("Maths", "", session_id)]

    def test_description_is_optional(self, client, session_id, headers):
        deck = client.post(decks_url(session_id), json={"name": "M"}, headers=headers).get_json()[
            "session_deck"
        ]
        assert deck["description"] == ""

    def test_name_is_trimmed(self, client, session_id, headers):
        deck = client.post(
            decks_url(session_id), json={"name": "  Maths "}, headers=headers
        ).get_json()["session_deck"]
        assert deck["name"] == "Maths"

    def test_two_decks_with_the_same_name_are_accepted(self, client, app, session_id, headers):
        for _ in range(2):
            assert (
                client.post(decks_url(session_id), json={"name": "Maths"}, headers=headers).status_code
                == 201
            )
        assert len(stored_decks(app, session_id)) == 2

    def test_the_client_cannot_choose_the_id_or_the_session(
        self, client, app, user, session_id, make_study_session, headers
    ):
        elsewhere = make_study_session(user["email"])
        body = {"name": "M", "session_deck_id": 999, "study_session_id": elsewhere}
        deck = client.post(decks_url(session_id), json=body, headers=headers).get_json()[
            "session_deck"
        ]
        assert deck["study_session_id"] == session_id
        assert deck["session_deck_id"] != 999
        assert stored_decks(app, elsewhere) == []

    def test_last_allowed_deck_is_accepted(self, client, session_id, headers, make_session_deck):
        for i in range(MAX_DECK_BY_SESSION - 1):
            make_session_deck(session_id, name=f"d{i}")
        assert (
            client.post(decks_url(session_id), json={"name": "last"}, headers=headers).status_code
            == 201
        )

    def test_deck_limit_returns_409(self, client, app, session_id, headers, make_session_deck):
        for i in range(MAX_DECK_BY_SESSION):
            make_session_deck(session_id, name=f"d{i}")
        response = client.post(decks_url(session_id), json={"name": "too many"}, headers=headers)
        assert response.status_code == 409
        assert response.get_json()["error"] == "SessionDeckLimitReached"
        assert len(stored_decks(app, session_id)) == MAX_DECK_BY_SESSION

    def test_the_limit_is_per_session(
        self, client, user, session_id, headers, make_study_session, make_session_deck
    ):
        for i in range(MAX_DECK_BY_SESSION):
            make_session_deck(session_id, name=f"d{i}")
        empty = make_study_session(user["email"])
        assert (
            client.post(decks_url(empty), json={"name": "ok"}, headers=headers).status_code == 201
        )

    def test_missing_name(self, client, session_id, headers):
        response = client.post(decks_url(session_id), json={"description": "d"}, headers=headers)
        assert response.status_code == 400
        assert response.get_json()["error"] == "InvalidRequest"

    @pytest.mark.parametrize("name", ["", "   "])
    def test_blank_name(self, client, session_id, headers, name):
        assert (
            client.post(decks_url(session_id), json={"name": name}, headers=headers).status_code
            == 400
        )

    @pytest.mark.parametrize("field", ["name", "description"])
    @pytest.mark.parametrize("value", [123, None, ["a"], {"a": 1}])
    def test_wrong_type(self, client, session_id, headers, field, value):
        body = {"name": "Maths", "description": "d", field: value}
        response = client.post(decks_url(session_id), json=body, headers=headers)
        assert response.status_code == 400
        assert response.get_json()["error"] == "InvalidRequest"

    @pytest.mark.parametrize(
        "kwargs",
        [{"data": "nope", "content_type": "application/json"}, {"json": ["a"]}, {"json": "t"}, {}],
    )
    def test_body_that_is_not_a_json_object(self, client, session_id, headers, kwargs):
        response = client.post(decks_url(session_id), headers=headers, **kwargs)
        assert response.status_code == 400
        assert response.get_json()["error"] == "InvalidRequest"

    def test_nothing_is_stored_when_validation_fails(self, client, app, session_id, headers):
        client.post(decks_url(session_id), json={"name": 1}, headers=headers)
        client.post(decks_url(session_id), json={}, headers=headers)
        assert stored_decks(app) == []

    def test_session_of_another_user_is_404_and_no_deck_created(
        self, client, app, foreign_session_id, headers
    ):
        response = client.post(decks_url(foreign_session_id), json={"name": "M"}, headers=headers)
        assert response.status_code == 404
        assert response.get_json()["error"] == "SessionNotFound"
        assert stored_decks(app) == []

    def test_unknown_session(self, client, headers):
        response = client.post(decks_url(99999), json={"name": "M"}, headers=headers)
        assert response.status_code == 404
        assert response.get_json()["error"] == "SessionNotFound"

    def test_other_users_session_and_unknown_session_are_indistinguishable(
        self, client, foreign_session_id, headers
    ):
        theirs = client.post(decks_url(foreign_session_id), json={"name": "M"}, headers=headers)
        unknown = client.post(decks_url(99999), json={"name": "M"}, headers=headers)
        assert theirs.status_code == unknown.status_code
        assert theirs.get_data() == unknown.get_data()

    def test_unknown_session_is_checked_before_the_body(self, client, headers):
        assert client.post(decks_url(99999), json={}, headers=headers).status_code == 404


class TestDelete:
    def test_deletes_the_deck(self, client, app, session_id, headers, make_session_deck):
        deck_id = make_session_deck(session_id)
        response = client.delete(deck_url(deck_id), headers=headers)
        assert response.status_code == 200
        assert response.get_json() == {"message": "Session deck deleted successfully"}
        assert stored_deck(app, deck_id) is None

    def test_its_cards_are_deleted_too(self, client, app, session_id, headers, make_session_deck):
        deck_id = make_session_deck(session_id, cards=[("q1", "a", "a"), ("q2", "a", "b")])
        assert stored_card_count(app) == 2
        client.delete(deck_url(deck_id), headers=headers)
        assert stored_card_count(app) == 0

    def test_sibling_decks_and_the_session_stay(
        self, client, app, session_id, headers, make_session_deck
    ):
        target = make_session_deck(session_id, name="Target", cards=[("q", "a", "a")])
        sibling = make_session_deck(session_id, name="Sibling", cards=[("q", "a", "a")])
        client.delete(deck_url(target), headers=headers)
        assert stored_deck(app, sibling) is not None
        assert session_exists(app, session_id)
        assert stored_card_count(app) == 1

    def test_deck_of_another_user_is_404_and_kept(
        self, client, app, foreign_session_id, headers, make_session_deck
    ):
        deck_id = make_session_deck(foreign_session_id, cards=[("q", "a", "a")])
        response = client.delete(deck_url(deck_id), headers=headers)
        assert response.status_code == 404
        assert response.get_json()["error"] == "SessionDeckNotFound"
        assert stored_deck(app, deck_id) is not None
        assert stored_card_count(app) == 1

    def test_unknown_deck(self, client, headers):
        response = client.delete(deck_url(99999), headers=headers)
        assert response.status_code == 404
        assert response.get_json()["error"] == "SessionDeckNotFound"

    def test_other_users_deck_and_unknown_deck_are_indistinguishable(
        self, client, foreign_session_id, headers, make_session_deck
    ):
        theirs = client.delete(deck_url(make_session_deck(foreign_session_id)), headers=headers)
        unknown = client.delete(deck_url(99999), headers=headers)
        assert theirs.status_code == unknown.status_code
        assert theirs.get_data() == unknown.get_data()

    def test_deleting_twice(self, client, session_id, headers, make_session_deck):
        deck_id = make_session_deck(session_id)
        assert client.delete(deck_url(deck_id), headers=headers).status_code == 200
        assert client.delete(deck_url(deck_id), headers=headers).status_code == 404

    def test_non_integer_id_is_404(self, client, headers):
        assert client.delete("/api/v1/session/deck/abc", headers=headers).status_code == 404


class TestMethodsAndPaths:
    def test_single_session_deck_allows_only_delete(
        self, client, session_id, headers, make_session_deck
    ):
        deck_id = make_session_deck(session_id)
        assert client.get(deck_url(deck_id), headers=headers).status_code == 405
        assert client.put(deck_url(deck_id), json={}, headers=headers).status_code == 405
        assert client.patch(deck_url(deck_id), json={}, headers=headers).status_code == 405
        assert client.post(deck_url(deck_id), json={}, headers=headers).status_code == 405

    def test_decks_collection_allows_only_get_and_post(self, client, session_id, headers):
        assert client.put(decks_url(session_id), json={}, headers=headers).status_code == 405
        assert client.patch(decks_url(session_id), json={}, headers=headers).status_code == 405
        assert client.delete(decks_url(session_id), headers=headers).status_code == 405
