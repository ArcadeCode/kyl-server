"""
POST/GET /api/v1/deck/<deck_id>/cards

Contract:
  - JSON card: {"card_id", "question", "answer", "is_tolerant", "position", "deck_id"}
  - POST body: question, answer, is_tolerant, position (all required) -> {"card": {...}}
  - question <= MAX_CARD_QUESTION_LENGTH, answer <= MAX_CARD_ANSWER_LENGTH, position >= 0
  - at most MAX_CARD_BY_DECK cards per deck
  - a deck of another account is a 404, exactly like an unknown id
"""

import pytest
from sqlalchemy import select

from consts import MAX_CARD_ANSWER_LENGTH, MAX_CARD_BY_DECK, MAX_CARD_QUESTION_LENGTH
from database import db
from models import Card
from tests.conftest import bearer

CARD_FIELDS = {"card_id", "question", "answer", "is_tolerant", "position", "deck_id"}
VALID = {"question": "1+1 ?", "answer": "2", "is_tolerant": False, "position": 0}


def cards_url(deck_id):
    return f"/api/v1/deck/{deck_id}/cards"


def stored_cards(app, deck_id=None):
    with app.app_context():
        query = select(Card)
        if deck_id is not None:
            query = query.where(Card.deck_id == deck_id)
        return [
            (c.question, c.answer, c.is_tolerant, c.position, c.deck_id)
            for c in db.session.scalars(query).all()
        ]


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
def deck_id(user, make_deck):
    return make_deck(user["email"], name="Maths")


class TestCreateCard:
    def test_returns_201_with_the_new_card(self, client, deck_id, headers):
        response = client.post(cards_url(deck_id), json=VALID, headers=headers)
        assert response.status_code == 201
        card = response.get_json()["card"]
        assert set(card) == CARD_FIELDS
        assert {k: card[k] for k in VALID} == VALID
        assert card["deck_id"] == deck_id
        assert isinstance(card["card_id"], int)

    def test_the_card_is_stored_in_this_deck(self, client, app, deck_id, headers):
        client.post(cards_url(deck_id), json=VALID, headers=headers)
        assert stored_cards(app) == [("1+1 ?", "2", False, 0, deck_id)]

    @pytest.mark.parametrize("is_tolerant", [True, False])
    def test_is_tolerant_is_kept_as_sent(self, client, app, deck_id, headers, is_tolerant):
        client.post(cards_url(deck_id), json={**VALID, "is_tolerant": is_tolerant}, headers=headers)
        assert stored_cards(app, deck_id)[0][2] is is_tolerant

    def test_the_client_cannot_choose_the_deck_or_the_id(self, client, app, user, make_deck, deck_id, headers):
        other_deck = make_deck(user["email"], name="Other deck")
        body = {**VALID, "deck_id": other_deck, "card_id": 999}
        card = client.post(cards_url(deck_id), json=body, headers=headers).get_json()["card"]
        assert card["deck_id"] == deck_id and card["card_id"] != 999
        assert stored_cards(app, other_deck) == []

    def test_several_cards_in_the_same_deck(self, client, app, deck_id, headers):
        for position in range(3):
            client.post(cards_url(deck_id), json={**VALID, "position": position}, headers=headers)
        assert sorted(c[3] for c in stored_cards(app, deck_id)) == [0, 1, 2]

    def test_question_and_answer_at_the_limit_are_accepted(self, client, deck_id, headers):
        body = {**VALID, "question": "q" * MAX_CARD_QUESTION_LENGTH, "answer": "a" * MAX_CARD_ANSWER_LENGTH}
        assert client.post(cards_url(deck_id), json=body, headers=headers).status_code == 201

    @pytest.mark.parametrize(
        "field, limit", [("question", MAX_CARD_QUESTION_LENGTH), ("answer", MAX_CARD_ANSWER_LENGTH)]
    )
    def test_text_over_the_limit_is_refused(self, client, app, deck_id, headers, field, limit):
        response = client.post(cards_url(deck_id), json={**VALID, field: "x" * (limit + 1)}, headers=headers)
        assert response.status_code == 400
        body = response.get_json()
        assert body["error"] == "InvalidRequest"
        assert body["message"].startswith(f"{field}:")
        assert stored_cards(app) == []

    @pytest.mark.parametrize("position", [-1, -50])
    def test_negative_position_is_refused(self, client, app, deck_id, headers, position):
        response = client.post(cards_url(deck_id), json={**VALID, "position": position}, headers=headers)
        assert response.status_code == 400
        assert response.get_json()["message"].startswith("position:")
        assert stored_cards(app) == []

    def test_position_zero_is_accepted(self, client, deck_id, headers):
        assert client.post(cards_url(deck_id), json={**VALID, "position": 0}, headers=headers).status_code == 201

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
            ("question", 1), ("question", None), ("answer", 1), ("answer", ["a"]),
            ("is_tolerant", "true"), ("is_tolerant", 1), ("position", "1"), ("position", 1.5),
            ("position", True),
        ],
    )
    def test_wrong_type(self, client, app, deck_id, headers, field, value):
        assert client.post(cards_url(deck_id), json={**VALID, field: value}, headers=headers).status_code == 400
        assert stored_cards(app) == []

    @pytest.mark.parametrize(
        "kwargs", [{"data": "nope", "content_type": "application/json"}, {"json": [1]}, {"json": "t"}, {}]
    )
    def test_body_that_is_not_a_json_object(self, client, deck_id, headers, kwargs):
        response = client.post(cards_url(deck_id), headers=headers, **kwargs)
        assert response.status_code == 400
        assert response.get_json()["error"] == "InvalidRequest"

    def test_last_allowed_card_is_accepted(self, client, user, make_deck, headers):
        deck = make_deck(user["email"], cards=[("q", "a")] * (MAX_CARD_BY_DECK - 1))
        assert client.post(cards_url(deck), json=VALID, headers=headers).status_code == 201

    def test_card_limit_returns_409(self, client, app, user, make_deck, headers):
        deck = make_deck(user["email"], cards=[("q", "a")] * MAX_CARD_BY_DECK)
        response = client.post(cards_url(deck), json=VALID, headers=headers)
        assert response.status_code == 409
        assert response.get_json()["error"] == "CardLimitReached"
        assert len(stored_cards(app, deck)) == MAX_CARD_BY_DECK

    def test_the_card_limit_is_per_deck(self, client, user, make_deck, headers):
        make_deck(user["email"], name="Full", cards=[("q", "a")] * MAX_CARD_BY_DECK)
        empty = make_deck(user["email"], name="Empty")
        assert client.post(cards_url(empty), json=VALID, headers=headers).status_code == 201

    def test_deck_of_another_user_is_404_and_no_card_created(self, client, app, other, make_deck, headers):
        deck = make_deck(other["email"])
        response = client.post(cards_url(deck), json=VALID, headers=headers)
        assert response.status_code == 404
        assert response.get_json()["error"] == "DeckNotFound"
        assert stored_cards(app) == []

    def test_unknown_deck(self, client, headers):
        response = client.post(cards_url(99999), json=VALID, headers=headers)
        assert response.status_code == 404
        assert response.get_json()["error"] == "DeckNotFound"

    def test_other_users_deck_and_unknown_deck_are_indistinguishable(self, client, other, make_deck, headers):
        theirs = client.post(cards_url(make_deck(other["email"])), json=VALID, headers=headers)
        unknown = client.post(cards_url(99999), json=VALID, headers=headers)
        assert theirs.status_code == unknown.status_code
        assert theirs.get_data() == unknown.get_data()

    def test_unknown_deck_is_checked_before_the_body(self, client, headers):
        assert client.post(cards_url(99999), json={}, headers=headers).status_code == 404


class TestListCards:
    def test_returns_the_cards_of_the_deck(self, client, user, make_deck, headers):
        deck = make_deck(user["email"], cards=[("q1", "a1"), ("q2", "a2")])
        response = client.get(cards_url(deck), headers=headers)
        assert response.status_code == 200
        assert [c["question"] for c in response.get_json()] == ["q1", "q2"]

    def test_card_shape(self, client, deck_id, make_card, headers):
        card_id = make_card(deck_id, "Q", "A", is_tolerant=False, position=3)
        (body,) = client.get(cards_url(deck_id), headers=headers).get_json()
        assert set(body) == CARD_FIELDS
        assert body == {
            "card_id": card_id, "question": "Q", "answer": "A",
            "is_tolerant": False, "position": 3, "deck_id": deck_id,
        }

    def test_cards_are_sorted_by_position(self, client, deck_id, make_card, headers):
        for position in (2, 0, 1):
            make_card(deck_id, question=f"q{position}", position=position)
        positions = [c["position"] for c in client.get(cards_url(deck_id), headers=headers).get_json()]
        assert positions == [0, 1, 2]

    def test_empty_deck(self, client, deck_id, headers):
        response = client.get(cards_url(deck_id), headers=headers)
        assert response.status_code == 200
        assert response.get_json() == []

    def test_only_the_cards_of_this_deck(self, client, user, make_deck, headers):
        mine = make_deck(user["email"], name="Mine", cards=[("mine", "a")])
        make_deck(user["email"], name="Another", cards=[("another", "a")])
        assert [c["question"] for c in client.get(cards_url(mine), headers=headers).get_json()] == ["mine"]

    def test_deck_of_another_user_is_404(self, client, other, make_deck, headers):
        deck = make_deck(other["email"], cards=[("secret", "a")])
        response = client.get(cards_url(deck), headers=headers)
        assert response.status_code == 404
        assert response.get_json()["error"] == "DeckNotFound"
        assert b"secret" not in response.get_data()

    def test_unknown_deck(self, client, headers):
        assert client.get(cards_url(99999), headers=headers).status_code == 404


def test_only_get_and_post_are_allowed(client, deck_id, headers):
    assert client.put(cards_url(deck_id), json={}, headers=headers).status_code == 405
    assert client.delete(cards_url(deck_id), headers=headers).status_code == 405
    assert client.patch(cards_url(deck_id), json={}, headers=headers).status_code == 405
