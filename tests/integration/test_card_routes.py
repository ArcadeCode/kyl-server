"""
GET/PATCH/DELETE /api/v1/card/<card_id>

Contract:
  - PATCH is partial: any subset of question, answer, is_tolerant, position (at least one);
    same validation rules as creation (length limits, position >= 0); returns the card, 200
  - DELETE returns 204 with an empty body and really removes the row
  - a card in a deck of another account is a 404, exactly like an unknown id
"""

import pytest
from sqlalchemy import select

from consts import MAX_CARD_ANSWER_LENGTH, MAX_CARD_QUESTION_LENGTH
from database import db
from models import Card, Deck
from tests.conftest import bearer

CARD_FIELDS = {"card_id", "question", "answer", "is_tolerant", "position", "deck_id"}


def card_url(card_id):
    return f"/api/v1/card/{card_id}"


def stored_card(app, card_id):
    with app.app_context():
        card = db.session.get(Card, card_id)
        if card is None:
            return None
        return (card.question, card.answer, card.is_tolerant, card.position, card.deck_id)


def deck_exists(app, deck_id):
    with app.app_context():
        return db.session.get(Deck, deck_id) is not None


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
    return make_deck(user["email"])


@pytest.fixture
def card_id(deck_id, make_card):
    return make_card(deck_id, question="Q", answer="A", is_tolerant=True, position=1)


@pytest.fixture
def foreign_card_id(other, make_deck, make_card):
    return make_card(make_deck(other["email"]), question="secret", answer="secret", position=0)


class TestGet:
    def test_returns_the_card(self, client, card_id, deck_id, headers):
        response = client.get(card_url(card_id), headers=headers)
        assert response.status_code == 200
        body = response.get_json()
        assert set(body) == CARD_FIELDS
        assert body == {
            "card_id": card_id, "question": "Q", "answer": "A",
            "is_tolerant": True, "position": 1, "deck_id": deck_id,
        }

    def test_card_of_another_user_is_404(self, client, foreign_card_id, headers):
        response = client.get(card_url(foreign_card_id), headers=headers)
        assert response.status_code == 404
        assert response.get_json()["error"] == "CardNotFound"
        assert b"secret" not in response.get_data()

    def test_unknown_card(self, client, headers):
        assert client.get(card_url(99999), headers=headers).status_code == 404

    def test_other_users_card_and_unknown_card_are_indistinguishable(self, client, foreign_card_id, headers):
        theirs = client.get(card_url(foreign_card_id), headers=headers)
        unknown = client.get(card_url(99999), headers=headers)
        assert theirs.status_code == unknown.status_code
        assert theirs.get_data() == unknown.get_data()

    def test_non_integer_id_is_404(self, client, headers):
        assert client.get("/api/v1/card/abc", headers=headers).status_code == 404


class TestUpdate:
    def test_updates_every_field(self, client, app, card_id, deck_id, headers):
        body = {"question": "Q2", "answer": "A2", "is_tolerant": False, "position": 5}
        response = client.patch(card_url(card_id), json=body, headers=headers)
        assert response.status_code == 200
        card = response.get_json()
        assert set(card) == CARD_FIELDS
        assert card["card_id"] == card_id and card["deck_id"] == deck_id
        assert stored_card(app, card_id) == ("Q2", "A2", False, 5, deck_id)

    @pytest.mark.parametrize(
        "change, expected",
        [
            ({"question": "new"}, ("new", "A", True, 1)),
            ({"answer": "new"}, ("Q", "new", True, 1)),
            ({"is_tolerant": False}, ("Q", "A", False, 1)),
            ({"position": 0}, ("Q", "A", True, 0)),
        ],
    )
    def test_partial_update_keeps_the_other_fields(self, client, app, card_id, deck_id, headers, change, expected):
        assert client.patch(card_url(card_id), json=change, headers=headers).status_code == 200
        assert stored_card(app, card_id) == (*expected, deck_id)

    def test_the_card_cannot_be_moved_to_another_deck(self, client, app, user, make_deck, card_id, deck_id, headers):
        elsewhere = make_deck(user["email"], name="Elsewhere")
        client.patch(card_url(card_id), json={"question": "N", "deck_id": elsewhere}, headers=headers)
        assert stored_card(app, card_id)[4] == deck_id

    def test_the_id_cannot_be_changed(self, client, app, card_id, headers):
        client.patch(card_url(card_id), json={"question": "N", "card_id": 999}, headers=headers)
        assert stored_card(app, card_id) is not None
        assert stored_card(app, 999) is None

    def test_question_and_answer_at_the_limit(self, client, card_id, headers):
        body = {"question": "q" * MAX_CARD_QUESTION_LENGTH, "answer": "a" * MAX_CARD_ANSWER_LENGTH}
        assert client.patch(card_url(card_id), json=body, headers=headers).status_code == 200

    @pytest.mark.parametrize(
        "field, limit", [("question", MAX_CARD_QUESTION_LENGTH), ("answer", MAX_CARD_ANSWER_LENGTH)]
    )
    def test_text_over_the_limit_is_refused_and_card_unchanged(self, client, app, card_id, deck_id, headers, field, limit):
        response = client.patch(card_url(card_id), json={field: "x" * (limit + 1)}, headers=headers)
        assert response.status_code == 400
        assert response.get_json()["message"].startswith(f"{field}:")
        assert stored_card(app, card_id) == ("Q", "A", True, 1, deck_id)

    @pytest.mark.parametrize("position", [-1, -50])
    def test_negative_position_is_refused_and_card_unchanged(self, client, app, card_id, deck_id, headers, position):
        response = client.patch(card_url(card_id), json={"position": position}, headers=headers)
        assert response.status_code == 400
        assert response.get_json()["message"].startswith("position:")
        assert stored_card(app, card_id) == ("Q", "A", True, 1, deck_id)

    @pytest.mark.parametrize(
        "field, value",
        [
            ("question", 1), ("question", None), ("answer", ["a"]), ("is_tolerant", "yes"),
            ("is_tolerant", 0), ("position", "2"), ("position", 1.5), ("position", True),
        ],
    )
    def test_wrong_type_is_refused_and_card_unchanged(self, client, app, card_id, deck_id, headers, field, value):
        assert client.patch(card_url(card_id), json={field: value}, headers=headers).status_code == 400
        assert stored_card(app, card_id) == ("Q", "A", True, 1, deck_id)

    def test_one_invalid_field_refuses_the_whole_update(self, client, app, card_id, deck_id, headers):
        response = client.patch(card_url(card_id), json={"question": "valid", "position": -1}, headers=headers)
        assert response.status_code == 400
        assert stored_card(app, card_id) == ("Q", "A", True, 1, deck_id)

    @pytest.mark.parametrize("body", [{}, {"unknown": 1}])
    def test_update_without_any_known_field(self, client, card_id, headers, body):
        response = client.patch(card_url(card_id), json=body, headers=headers)
        assert response.status_code == 400
        assert response.get_json()["error"] == "InvalidRequest"

    @pytest.mark.parametrize(
        "kwargs", [{"data": "nope", "content_type": "application/json"}, {"json": [1]}, {"json": "t"}, {}]
    )
    def test_body_that_is_not_a_json_object(self, client, card_id, headers, kwargs):
        assert client.patch(card_url(card_id), headers=headers, **kwargs).status_code == 400

    def test_card_of_another_user_is_404_and_untouched(self, client, app, foreign_card_id, other, headers):
        response = client.patch(card_url(foreign_card_id), json={"question": "Hacked"}, headers=headers)
        assert response.status_code == 404
        assert response.get_json()["error"] == "CardNotFound"
        assert stored_card(app, foreign_card_id)[0] == "secret"

    def test_unknown_card(self, client, headers):
        assert client.patch(card_url(99999), json={"question": "N"}, headers=headers).status_code == 404

    def test_unknown_card_is_checked_before_the_body(self, client, headers):
        assert client.patch(card_url(99999), json={}, headers=headers).status_code == 404

    def test_other_cards_are_untouched(self, client, app, deck_id, card_id, make_card, headers):
        sibling = make_card(deck_id, question="S", answer="S", position=2)
        client.patch(card_url(card_id), json={"question": "N"}, headers=headers)
        assert stored_card(app, sibling) == ("S", "S", True, 2, deck_id)


class TestDelete:
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

    def test_the_deck_and_sibling_cards_stay(self, client, app, deck_id, card_id, make_card, headers):
        sibling = make_card(deck_id, question="S", answer="S", position=2)
        client.delete(card_url(card_id), headers=headers)
        assert deck_exists(app, deck_id)
        assert stored_card(app, sibling) is not None

    def test_card_of_another_user_is_404_and_kept(self, client, app, foreign_card_id, headers):
        response = client.delete(card_url(foreign_card_id), headers=headers)
        assert response.status_code == 404
        assert response.get_json()["error"] == "CardNotFound"
        assert stored_card(app, foreign_card_id) is not None

    def test_unknown_card(self, client, headers):
        assert client.delete(card_url(99999), headers=headers).status_code == 404


def test_post_and_put_are_not_allowed(client, card_id, headers):
    assert client.post(card_url(card_id), json={}, headers=headers).status_code == 405
    assert client.put(card_url(card_id), json={}, headers=headers).status_code == 405
