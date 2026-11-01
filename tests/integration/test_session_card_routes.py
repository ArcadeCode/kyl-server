"""
GET/POST /api/v1/session/deck/<id>/cards, GET/DELETE /api/v1/session/card/<id>

Contract:
  - JSON session card: {"session_card_id", "question", "correct_answer", "user_answer",
    "is_tolerant", "position", "session_deck_id"}
  - POST body: question, correct_answer, user_answer, is_tolerant, position (all required)
    -> {"session_card": {...}}
  - question <= MAX_CARD_QUESTION_LENGTH, answers <= MAX_CARD_ANSWER_LENGTH, position >= 0,
    user_answer may be empty (skipped question)
  - at most MAX_CARD_BY_DECK cards per session deck
  - snapshots are immutable: no PATCH
  - anything under a session of another account is a 404, exactly like an unknown id
"""

import pytest
from sqlalchemy import select

from consts import MAX_CARD_ANSWER_LENGTH, MAX_CARD_BY_DECK, MAX_CARD_QUESTION_LENGTH
from database import db
from models import SessionCard, SessionDeck, StudySession
from tests.conftest import bearer

CARD_FIELDS = {
    "session_card_id", "question", "correct_answer", "user_answer",
    "is_tolerant", "position", "session_deck_id",
}
VALID = {
    "question": "1+1 ?",
    "correct_answer": "2",
    "user_answer": "3",
    "is_tolerant": False,
    "position": 0,
}


def cards_url(session_deck_id):
    return f"/api/v1/session/deck/{session_deck_id}/cards"


def card_url(session_card_id):
    return f"/api/v1/session/card/{session_card_id}"


def stored_cards(app, session_deck_id=None):
    with app.app_context():
        query = select(SessionCard)
        if session_deck_id is not None:
            query = query.where(SessionCard.session_deck_id == session_deck_id)
        return [
            (c.question, c.correct_answer, c.user_answer, c.is_tolerant, c.position, c.session_deck_id)
            for c in db.session.scalars(query).all()
        ]


def stored_card(app, session_card_id):
    with app.app_context():
        card = db.session.get(SessionCard, session_card_id)
        if card is None:
            return None
        return (
            card.question, card.correct_answer, card.user_answer,
            card.is_tolerant, card.position, card.session_deck_id,
        )


def exists(app, model, pk):
    with app.app_context():
        return db.session.get(model, pk) is not None


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
def deck_id(session_id, make_session_deck):
    return make_session_deck(session_id, name="Maths")


@pytest.fixture
def card_id(deck_id, make_session_card):
    return make_session_card(
        deck_id, question="Q", correct_answer="A", user_answer="B", is_tolerant=True, position=1
    )


@pytest.fixture
def foreign_deck_id(other, make_study_session, make_session_deck):
    return make_session_deck(make_study_session(other["email"]), name="Theirs")


@pytest.fixture
def foreign_card_id(foreign_deck_id, make_session_card):
    return make_session_card(
        foreign_deck_id, question="secret", correct_answer="secret", user_answer="secret"
    )


class TestListCards:
    def test_returns_the_cards_of_the_deck(self, client, session_id, headers, make_session_deck):
        deck = make_session_deck(session_id, cards=[("q1", "a1", "u1"), ("q2", "a2", "u2")])
        response = client.get(cards_url(deck), headers=headers)
        assert response.status_code == 200
        assert [c["question"] for c in response.get_json()] == ["q1", "q2"]

    def test_card_shape(self, client, deck_id, headers, make_session_card):
        card = make_session_card(deck_id, "Q", "A", "U", is_tolerant=False, position=3)
        (body,) = client.get(cards_url(deck_id), headers=headers).get_json()
        assert set(body) == CARD_FIELDS
        assert body == {
            "session_card_id": card, "question": "Q", "correct_answer": "A", "user_answer": "U",
            "is_tolerant": False, "position": 3, "session_deck_id": deck_id,
        }

    def test_cards_are_sorted_by_position(self, client, deck_id, headers, make_session_card):
        for position in (2, 0, 1):
            make_session_card(deck_id, question=f"q{position}", position=position)
        positions = [c["position"] for c in client.get(cards_url(deck_id), headers=headers).get_json()]
        assert positions == [0, 1, 2]

    def test_empty_deck(self, client, deck_id, headers):
        response = client.get(cards_url(deck_id), headers=headers)
        assert response.status_code == 200
        assert response.get_json() == []

    def test_only_the_cards_of_this_deck(self, client, session_id, headers, make_session_deck):
        mine = make_session_deck(session_id, name="Mine", cards=[("mine", "a", "a")])
        make_session_deck(session_id, name="Another", cards=[("another", "a", "a")])
        questions = [c["question"] for c in client.get(cards_url(mine), headers=headers).get_json()]
        assert questions == ["mine"]

    def test_deck_of_another_user_is_404_without_leak(
        self, client, foreign_deck_id, headers, make_session_card
    ):
        make_session_card(foreign_deck_id, question="secret")
        response = client.get(cards_url(foreign_deck_id), headers=headers)
        assert response.status_code == 404
        assert response.get_json()["error"] == "SessionDeckNotFound"
        assert b"secret" not in response.get_data()

    def test_unknown_deck(self, client, headers):
        response = client.get(cards_url(99999), headers=headers)
        assert response.status_code == 404
        assert response.get_json()["error"] == "SessionDeckNotFound"


class TestCreateCard:
    def test_returns_201_with_the_new_card(self, client, deck_id, headers):
        response = client.post(cards_url(deck_id), json=VALID, headers=headers)
        assert response.status_code == 201
        card = response.get_json()["session_card"]
        assert set(card) == CARD_FIELDS
        assert {k: card[k] for k in VALID} == VALID
        assert card["session_deck_id"] == deck_id
        assert isinstance(card["session_card_id"], int)

    def test_the_card_is_stored_in_this_deck(self, client, app, deck_id, headers):
        client.post(cards_url(deck_id), json=VALID, headers=headers)
        assert stored_cards(app) == [("1+1 ?", "2", "3", False, 0, deck_id)]

    @pytest.mark.parametrize("is_tolerant", [True, False])
    def test_is_tolerant_is_kept_as_sent(self, client, app, deck_id, headers, is_tolerant):
        client.post(cards_url(deck_id), json={**VALID, "is_tolerant": is_tolerant}, headers=headers)
        assert stored_cards(app, deck_id)[0][3] is is_tolerant

    def test_the_client_cannot_choose_the_deck_or_the_id(
        self, client, app, session_id, deck_id, headers, make_session_deck
    ):
        other_deck = make_session_deck(session_id, name="Other deck")
        body = {**VALID, "session_deck_id": other_deck, "session_card_id": 999}
        card = client.post(cards_url(deck_id), json=body, headers=headers).get_json()["session_card"]
        assert card["session_deck_id"] == deck_id and card["session_card_id"] != 999
        assert stored_cards(app, other_deck) == []

    def test_several_cards_in_the_same_deck(self, client, app, deck_id, headers):
        for position in range(3):
            client.post(cards_url(deck_id), json={**VALID, "position": position}, headers=headers)
        assert sorted(c[4] for c in stored_cards(app, deck_id)) == [0, 1, 2]

    def test_texts_at_the_limit_are_accepted(self, client, deck_id, headers):
        body = {
            **VALID,
            "question": "q" * MAX_CARD_QUESTION_LENGTH,
            "correct_answer": "a" * MAX_CARD_ANSWER_LENGTH,
            "user_answer": "u" * MAX_CARD_ANSWER_LENGTH,
        }
        assert client.post(cards_url(deck_id), json=body, headers=headers).status_code == 201

    @pytest.mark.parametrize(
        "field, limit",
        [
            ("question", MAX_CARD_QUESTION_LENGTH),
            ("correct_answer", MAX_CARD_ANSWER_LENGTH),
            ("user_answer", MAX_CARD_ANSWER_LENGTH),
        ],
    )
    def test_text_over_the_limit_is_refused(self, client, app, deck_id, headers, field, limit):
        response = client.post(
            cards_url(deck_id), json={**VALID, field: "x" * (limit + 1)}, headers=headers
        )
        assert response.status_code == 400
        body = response.get_json()
        assert body["error"] == "InvalidRequest"
        assert body["message"].startswith(f"{field}:")
        assert stored_cards(app) == []

    def test_empty_user_answer_is_accepted(self, client, app, deck_id, headers):
        response = client.post(
            cards_url(deck_id), json={**VALID, "user_answer": ""}, headers=headers
        )
        assert response.status_code == 201
        assert stored_cards(app, deck_id)[0][2] == ""

    @pytest.mark.parametrize("position", [-1, -50])
    def test_negative_position_is_refused(self, client, app, deck_id, headers, position):
        response = client.post(
            cards_url(deck_id), json={**VALID, "position": position}, headers=headers
        )
        assert response.status_code == 400
        assert response.get_json()["message"].startswith("position:")
        assert stored_cards(app) == []

    def test_position_zero_is_accepted(self, client, deck_id, headers):
        response = client.post(cards_url(deck_id), json={**VALID, "position": 0}, headers=headers)
        assert response.status_code == 201

    @pytest.mark.parametrize("missing", list(VALID))
    def test_missing_field(self, client, app, deck_id, headers, missing):
        body = {k: v for k, v in VALID.items() if k != missing}
        response = client.post(cards_url(deck_id), json=body, headers=headers)
        assert response.status_code == 400
        assert response.get_json()["error"] == "InvalidRequest"
        assert response.get_json()["message"].startswith(f"{missing}:")
        assert stored_cards(app) == []

    @pytest.mark.parametrize(
        "field, value",
        [
            ("question", 1), ("question", None),
            ("correct_answer", 1), ("correct_answer", ["a"]),
            ("user_answer", 1), ("user_answer", None),
            ("is_tolerant", "true"), ("is_tolerant", 1),
            ("position", "1"), ("position", 1.5), ("position", True),
        ],
    )
    def test_wrong_type(self, client, app, deck_id, headers, field, value):
        response = client.post(cards_url(deck_id), json={**VALID, field: value}, headers=headers)
        assert response.status_code == 400
        assert stored_cards(app) == []

    @pytest.mark.parametrize(
        "kwargs",
        [{"data": "nope", "content_type": "application/json"}, {"json": [1]}, {"json": "t"}, {}],
    )
    def test_body_that_is_not_a_json_object(self, client, deck_id, headers, kwargs):
        response = client.post(cards_url(deck_id), headers=headers, **kwargs)
        assert response.status_code == 400
        assert response.get_json()["error"] == "InvalidRequest"

    def test_last_allowed_card_is_accepted(self, client, session_id, headers, make_session_deck):
        deck = make_session_deck(session_id, cards=[("q", "a", "a")] * (MAX_CARD_BY_DECK - 1))
        assert client.post(cards_url(deck), json=VALID, headers=headers).status_code == 201

    def test_card_limit_returns_409(self, client, app, session_id, headers, make_session_deck):
        deck = make_session_deck(session_id, cards=[("q", "a", "a")] * MAX_CARD_BY_DECK)
        response = client.post(cards_url(deck), json=VALID, headers=headers)
        assert response.status_code == 409
        assert response.get_json()["error"] == "SessionCardLimitReached"
        assert len(stored_cards(app, deck)) == MAX_CARD_BY_DECK

    def test_the_card_limit_is_per_deck(self, client, session_id, headers, make_session_deck):
        make_session_deck(session_id, name="Full", cards=[("q", "a", "a")] * MAX_CARD_BY_DECK)
        empty = make_session_deck(session_id, name="Empty")
        assert client.post(cards_url(empty), json=VALID, headers=headers).status_code == 201

    def test_deck_of_another_user_is_404_and_no_card_created(
        self, client, app, foreign_deck_id, headers
    ):
        response = client.post(cards_url(foreign_deck_id), json=VALID, headers=headers)
        assert response.status_code == 404
        assert response.get_json()["error"] == "SessionDeckNotFound"
        assert stored_cards(app) == []

    def test_unknown_deck(self, client, headers):
        response = client.post(cards_url(99999), json=VALID, headers=headers)
        assert response.status_code == 404
        assert response.get_json()["error"] == "SessionDeckNotFound"

    def test_other_users_deck_and_unknown_deck_are_indistinguishable(
        self, client, foreign_deck_id, headers
    ):
        theirs = client.post(cards_url(foreign_deck_id), json=VALID, headers=headers)
        unknown = client.post(cards_url(99999), json=VALID, headers=headers)
        assert theirs.status_code == unknown.status_code
        assert theirs.get_data() == unknown.get_data()

    def test_unknown_deck_is_checked_before_the_body(self, client, headers):
        assert client.post(cards_url(99999), json={}, headers=headers).status_code == 404


class TestGetCard:
    def test_returns_the_card(self, client, card_id, deck_id, headers):
        response = client.get(card_url(card_id), headers=headers)
        assert response.status_code == 200
        body = response.get_json()
        assert set(body) == CARD_FIELDS
        assert body == {
            "session_card_id": card_id, "question": "Q", "correct_answer": "A", "user_answer": "B",
            "is_tolerant": True, "position": 1, "session_deck_id": deck_id,
        }

    def test_card_of_another_user_is_404_without_leak(self, client, foreign_card_id, headers):
        response = client.get(card_url(foreign_card_id), headers=headers)
        assert response.status_code == 404
        assert response.get_json()["error"] == "SessionCardNotFound"
        assert b"secret" not in response.get_data()

    def test_unknown_card(self, client, headers):
        assert client.get(card_url(99999), headers=headers).status_code == 404

    def test_other_users_card_and_unknown_card_are_indistinguishable(
        self, client, foreign_card_id, headers
    ):
        theirs = client.get(card_url(foreign_card_id), headers=headers)
        unknown = client.get(card_url(99999), headers=headers)
        assert theirs.status_code == unknown.status_code
        assert theirs.get_data() == unknown.get_data()

    def test_non_integer_id_is_404(self, client, headers):
        assert client.get("/api/v1/session/card/abc", headers=headers).status_code == 404

    def test_ownership_goes_through_the_study_session(
        self, client, user, other, make_token, card_id, foreign_card_id
    ):
        """Each user reads his own card and only his own, whatever the ids look like."""
        mine, theirs = bearer(make_token(user["email"])), bearer(make_token(other["email"]))
        assert client.get(card_url(card_id), headers=mine).status_code == 200
        assert client.get(card_url(foreign_card_id), headers=mine).status_code == 404
        assert client.get(card_url(foreign_card_id), headers=theirs).status_code == 200
        assert client.get(card_url(card_id), headers=theirs).status_code == 404


class TestDeleteCard:
    def test_returns_204_with_an_empty_body(self, client, card_id, headers):
        response = client.delete(card_url(card_id), headers=headers)
        assert response.status_code == 204
        assert response.get_data() == b""

    def test_the_row_is_really_deleted(self, client, app, card_id, headers):
        client.delete(card_url(card_id), headers=headers)
        assert stored_card(app, card_id) is None

    def test_the_card_is_gone_for_later_requests(self, client, card_id, headers):
        client.delete(card_url(card_id), headers=headers)
        assert client.get(card_url(card_id), headers=headers).status_code == 404
        assert client.delete(card_url(card_id), headers=headers).status_code == 404

    def test_deck_session_and_sibling_cards_stay(
        self, client, app, session_id, deck_id, card_id, headers, make_session_card
    ):
        sibling = make_session_card(deck_id, question="S", position=2)
        client.delete(card_url(card_id), headers=headers)
        assert exists(app, SessionDeck, deck_id)
        assert exists(app, StudySession, session_id)
        assert stored_card(app, sibling) is not None

    def test_card_of_another_user_is_404_and_kept(self, client, app, foreign_card_id, headers):
        response = client.delete(card_url(foreign_card_id), headers=headers)
        assert response.status_code == 404
        assert response.get_json()["error"] == "SessionCardNotFound"
        assert stored_card(app, foreign_card_id) is not None

    def test_unknown_card(self, client, headers):
        assert client.delete(card_url(99999), headers=headers).status_code == 404


class TestMethodsAndPaths:
    def test_single_card_allows_only_get_and_delete(self, client, card_id, headers):
        assert client.post(card_url(card_id), json={}, headers=headers).status_code == 405
        assert client.put(card_url(card_id), json={}, headers=headers).status_code == 405
        assert client.patch(card_url(card_id), json={}, headers=headers).status_code == 405

    def test_cards_collection_allows_only_get_and_post(self, client, deck_id, headers):
        assert client.put(cards_url(deck_id), json={}, headers=headers).status_code == 405
        assert client.patch(cards_url(deck_id), json={}, headers=headers).status_code == 405
        assert client.delete(cards_url(deck_id), headers=headers).status_code == 405
