"""
GET/POST /api/v1/decks, PATCH/DELETE /api/v1/deck/<id>

Contract:
  - JSON deck: {"deck_id", "name", "description", "owner_email"}
  - POST creates a deck (no id in the URL), body {"name", "description"?}
  - PATCH is partial: any subset of name / description, at least one
  - a deck of another account is a 404, exactly like an unknown id
"""

import pytest
from sqlalchemy import select

from consts import MAX_DECK_BY_USER
from database import db
from models import Card, Deck
from tests.conftest import bearer

DECKS = "/api/v1/decks"
DECK_FIELDS = {"deck_id", "name", "description", "owner_email"}


def deck_url(deck_id):
    return f"/api/v1/deck/{deck_id}"


def stored_decks(app, email=None):
    with app.app_context():
        query = select(Deck)
        if email:
            query = query.where(Deck.owner_email == email)
        return db.session.scalars(query).all()


def stored_deck(app, deck_id):
    with app.app_context():
        deck = db.session.get(Deck, deck_id)
        return None if deck is None else (deck.name, deck.description, deck.owner_email)


def stored_card_count(app):
    with app.app_context():
        return len(db.session.scalars(select(Card)).all())


@pytest.fixture
def user(make_account):
    return make_account()


@pytest.fixture
def other(make_account):
    return make_account(email="other@example.com")


@pytest.fixture
def headers(user, make_token):
    return bearer(make_token(user["email"]))


class TestList:
    def test_returns_only_my_decks(self, client, user, other, headers, make_deck):
        make_deck(user["email"], name="Maths")
        make_deck(other["email"], name="Secret")
        response = client.get(DECKS, headers=headers)
        assert response.status_code == 200
        assert [d["name"] for d in response.get_json()] == ["Maths"]

    def test_empty_list_when_no_deck(self, client, headers):
        response = client.get(DECKS, headers=headers)
        assert response.status_code == 200
        assert response.get_json() == []

    def test_deck_shape(self, client, user, headers, make_deck):
        deck_id = make_deck(user["email"], name="Maths", description="Chap. 1")
        (body,) = client.get(DECKS, headers=headers).get_json()
        assert set(body) == DECK_FIELDS
        assert body == {
            "deck_id": deck_id, "name": "Maths", "description": "Chap. 1", "owner_email": user["email"],
        }

    def test_several_decks(self, client, user, headers, make_deck):
        for name in ("A", "B", "C"):
            make_deck(user["email"], name=name)
        names = {d["name"] for d in client.get(DECKS, headers=headers).get_json()}
        assert names == {"A", "B", "C"}


class TestCreate:
    def test_returns_201_with_the_new_deck(self, client, user, headers):
        response = client.post(DECKS, json={"name": "Maths", "description": "Chap. 1"}, headers=headers)
        assert response.status_code == 201
        deck = response.get_json()["deck"]
        assert set(deck) == DECK_FIELDS
        assert (deck["name"], deck["description"], deck["owner_email"]) == (
            "Maths", "Chap. 1", user["email"],
        )

    def test_the_deck_is_stored_for_the_caller(self, client, app, user, headers):
        deck_id = client.post(DECKS, json={"name": "Maths"}, headers=headers).get_json()["deck"]["deck_id"]
        assert stored_deck(app, deck_id) == ("Maths", "", user["email"])

    def test_description_is_optional(self, client, headers):
        deck = client.post(DECKS, json={"name": "Maths"}, headers=headers).get_json()["deck"]
        assert deck["description"] == ""

    def test_name_is_trimmed(self, client, headers):
        deck = client.post(DECKS, json={"name": "  Maths "}, headers=headers).get_json()["deck"]
        assert deck["name"] == "Maths"

    def test_the_client_cannot_choose_the_owner_or_the_id(self, client, app, user, other, headers):
        body = {"name": "Maths", "owner_email": other["email"], "deck_id": 999}
        deck = client.post(DECKS, json=body, headers=headers).get_json()["deck"]
        assert deck["owner_email"] == user["email"]
        assert deck["deck_id"] != 999
        assert stored_decks(app, other["email"]) == []

    def test_each_creation_gives_a_distinct_id(self, client, headers):
        first = client.post(DECKS, json={"name": "A"}, headers=headers).get_json()["deck"]["deck_id"]
        second = client.post(DECKS, json={"name": "B"}, headers=headers).get_json()["deck"]["deck_id"]
        assert first != second

    def test_duplicate_name_returns_409(self, client, app, user, headers, make_deck):
        make_deck(user["email"], name="Maths")
        response = client.post(DECKS, json={"name": "Maths"}, headers=headers)
        assert response.status_code == 409
        assert response.get_json()["error"] == "Conflict"
        assert len(stored_decks(app, user["email"])) == 1

    def test_duplicate_detection_ignores_surrounding_spaces(self, client, user, headers, make_deck):
        make_deck(user["email"], name="Maths")
        assert client.post(DECKS, json={"name": " Maths "}, headers=headers).status_code == 409

    def test_same_name_as_another_users_deck_is_accepted(self, client, user, other, headers, make_deck):
        make_deck(other["email"], name="Maths")
        assert client.post(DECKS, json={"name": "Maths"}, headers=headers).status_code == 201

    def test_last_allowed_deck_is_accepted(self, client, user, headers, make_deck):
        for i in range(MAX_DECK_BY_USER - 1):
            make_deck(user["email"], name=f"d{i}")
        assert client.post(DECKS, json={"name": "last"}, headers=headers).status_code == 201

    def test_deck_limit_returns_409(self, client, app, user, headers, make_deck):
        for i in range(MAX_DECK_BY_USER):
            make_deck(user["email"], name=f"d{i}")
        response = client.post(DECKS, json={"name": "one too many"}, headers=headers)
        assert response.status_code == 409
        assert response.get_json()["error"] == "DeckLimitReached"
        assert len(stored_decks(app, user["email"])) == MAX_DECK_BY_USER

    def test_the_limit_is_per_user(self, client, user, other, headers, make_deck):
        for i in range(MAX_DECK_BY_USER):
            make_deck(other["email"], name=f"d{i}")
        assert client.post(DECKS, json={"name": "mine"}, headers=headers).status_code == 201

    def test_missing_name(self, client, headers):
        response = client.post(DECKS, json={"description": "d"}, headers=headers)
        assert response.status_code == 400
        assert response.get_json()["error"] == "InvalidRequest"

    @pytest.mark.parametrize("name", ["", "   "])
    def test_blank_name(self, client, headers, name):
        assert client.post(DECKS, json={"name": name}, headers=headers).status_code == 400

    @pytest.mark.parametrize("field", ["name", "description"])
    @pytest.mark.parametrize("value", [123, None, ["a"], {"a": 1}])
    def test_wrong_type(self, client, headers, field, value):
        body = {"name": "Maths", "description": "d", field: value}
        response = client.post(DECKS, json=body, headers=headers)
        assert response.status_code == 400
        assert response.get_json()["error"] == "InvalidRequest"

    @pytest.mark.parametrize(
        "kwargs",
        [{"data": "nope", "content_type": "application/json"}, {"json": ["a"]}, {"json": "text"}, {}],
    )
    def test_body_that_is_not_a_json_object(self, client, headers, kwargs):
        assert client.post(DECKS, headers=headers, **kwargs).status_code == 400

    def test_nothing_is_stored_when_validation_fails(self, client, app, headers):
        client.post(DECKS, json={"name": 1}, headers=headers)
        client.post(DECKS, json={}, headers=headers)
        assert stored_decks(app) == []

    def test_error_body_has_a_code_and_a_message(self, client, headers):
        body = client.post(DECKS, json={}, headers=headers).get_json()
        assert set(body) == {"error", "message"}


class TestUpdate:
    def test_updates_name_and_description(self, client, app, user, headers, make_deck):
        deck_id = make_deck(user["email"], name="Old", description="old")
        response = client.patch(deck_url(deck_id), json={"name": "New", "description": "new"}, headers=headers)
        assert response.status_code == 200
        deck = response.get_json()["deck"]
        assert set(deck) == DECK_FIELDS
        assert (deck["deck_id"], deck["name"], deck["description"]) == (deck_id, "New", "new")
        assert stored_deck(app, deck_id) == ("New", "new", user["email"])

    def test_partial_update_keeps_the_other_field(self, client, app, user, headers, make_deck):
        deck_id = make_deck(user["email"], name="Keep", description="old")
        client.patch(deck_url(deck_id), json={"description": "new"}, headers=headers)
        assert stored_deck(app, deck_id) == ("Keep", "new", user["email"])
        client.patch(deck_url(deck_id), json={"name": "Renamed"}, headers=headers)
        assert stored_deck(app, deck_id) == ("Renamed", "new", user["email"])

    def test_description_can_be_emptied(self, client, app, user, headers, make_deck):
        deck_id = make_deck(user["email"], description="old")
        assert client.patch(deck_url(deck_id), json={"description": ""}, headers=headers).status_code == 200
        assert stored_deck(app, deck_id)[1] == ""

    def test_the_owner_cannot_be_changed(self, client, app, user, other, headers, make_deck):
        deck_id = make_deck(user["email"])
        client.patch(deck_url(deck_id), json={"name": "N", "owner_email": other["email"]}, headers=headers)
        assert stored_deck(app, deck_id)[2] == user["email"]

    def test_keeping_its_own_name_is_not_a_conflict(self, client, user, headers, make_deck):
        deck_id = make_deck(user["email"], name="Maths")
        assert client.patch(deck_url(deck_id), json={"name": "Maths"}, headers=headers).status_code == 200

    def test_renaming_to_another_of_my_decks_names_returns_409(self, client, app, user, headers, make_deck):
        make_deck(user["email"], name="Taken")
        deck_id = make_deck(user["email"], name="Mine")
        response = client.patch(deck_url(deck_id), json={"name": "Taken"}, headers=headers)
        assert response.status_code == 409
        assert response.get_json()["error"] == "Conflict"
        assert stored_deck(app, deck_id)[0] == "Mine"

    def test_renaming_to_a_name_used_by_another_user_is_accepted(self, client, user, other, headers, make_deck):
        make_deck(other["email"], name="Taken")
        deck_id = make_deck(user["email"], name="Mine")
        assert client.patch(deck_url(deck_id), json={"name": "Taken"}, headers=headers).status_code == 200

    def test_deck_of_another_user_is_404_and_untouched(self, client, app, other, headers, make_deck):
        deck_id = make_deck(other["email"], name="Secret", description="s")
        response = client.patch(deck_url(deck_id), json={"name": "Hacked"}, headers=headers)
        assert response.status_code == 404
        assert response.get_json()["error"] == "DeckNotFound"
        assert stored_deck(app, deck_id) == ("Secret", "s", other["email"])

    def test_unknown_deck(self, client, headers):
        response = client.patch(deck_url(99999), json={"name": "N"}, headers=headers)
        assert response.status_code == 404
        assert response.get_json()["error"] == "DeckNotFound"

    def test_other_users_deck_and_unknown_deck_are_indistinguishable(self, client, other, headers, make_deck):
        theirs = client.patch(deck_url(make_deck(other["email"])), json={"name": "N"}, headers=headers)
        unknown = client.patch(deck_url(99999), json={"name": "N"}, headers=headers)
        assert theirs.status_code == unknown.status_code
        assert theirs.get_data() == unknown.get_data()

    @pytest.mark.parametrize("body", [{}, {"unknown": 1}])
    def test_update_without_any_known_field(self, client, user, headers, make_deck, body):
        deck_id = make_deck(user["email"])
        response = client.patch(deck_url(deck_id), json=body, headers=headers)
        assert response.status_code == 400
        assert response.get_json()["error"] == "InvalidRequest"

    @pytest.mark.parametrize("field", ["name", "description"])
    @pytest.mark.parametrize("value", [123, None, ["a"]])
    def test_wrong_type_leaves_the_deck_unchanged(self, client, app, user, headers, make_deck, field, value):
        deck_id = make_deck(user["email"], name="Keep", description="keep")
        assert client.patch(deck_url(deck_id), json={field: value}, headers=headers).status_code == 400
        assert stored_deck(app, deck_id) == ("Keep", "keep", user["email"])

    def test_blank_name(self, client, user, headers, make_deck):
        deck_id = make_deck(user["email"])
        assert client.patch(deck_url(deck_id), json={"name": "  "}, headers=headers).status_code == 400

    @pytest.mark.parametrize("kwargs", [{"data": "nope", "content_type": "application/json"}, {"json": [1]}, {}])
    def test_body_that_is_not_a_json_object(self, client, user, headers, make_deck, kwargs):
        deck_id = make_deck(user["email"])
        assert client.patch(deck_url(deck_id), headers=headers, **kwargs).status_code == 400


class TestDelete:
    def test_deletes_the_deck(self, client, app, user, headers, make_deck):
        deck_id = make_deck(user["email"])
        response = client.delete(deck_url(deck_id), headers=headers)
        assert response.status_code == 200
        assert stored_deck(app, deck_id) is None

    def test_its_cards_are_deleted_too(self, client, app, user, headers, make_deck):
        deck_id = make_deck(user["email"], cards=[("q1", "a1"), ("q2", "a2")])
        assert stored_card_count(app) == 2
        client.delete(deck_url(deck_id), headers=headers)
        assert stored_card_count(app) == 0

    def test_other_decks_and_their_cards_are_intact(self, client, app, user, other, headers, make_deck):
        target = make_deck(user["email"], name="Target", cards=[("q", "a")])
        mine = make_deck(user["email"], name="Mine", cards=[("q", "a")])
        theirs = make_deck(other["email"], name="Theirs", cards=[("q", "a")])
        client.delete(deck_url(target), headers=headers)
        assert stored_deck(app, mine) is not None
        assert stored_deck(app, theirs) is not None
        assert stored_card_count(app) == 2

    def test_deck_of_another_user_is_404_and_kept(self, client, app, other, headers, make_deck):
        deck_id = make_deck(other["email"], cards=[("q", "a")])
        response = client.delete(deck_url(deck_id), headers=headers)
        assert response.status_code == 404
        assert response.get_json()["error"] == "DeckNotFound"
        assert stored_deck(app, deck_id) is not None
        assert stored_card_count(app) == 1

    def test_unknown_deck(self, client, headers):
        assert client.delete(deck_url(99999), headers=headers).status_code == 404

    def test_deleting_twice(self, client, user, headers, make_deck):
        deck_id = make_deck(user["email"])
        assert client.delete(deck_url(deck_id), headers=headers).status_code == 200
        assert client.delete(deck_url(deck_id), headers=headers).status_code == 404


class TestMethodsAndPaths:
    def test_decks_collection_allows_only_get_and_post(self, client, headers):
        assert client.put(DECKS, json={}, headers=headers).status_code == 405
        assert client.delete(DECKS, headers=headers).status_code == 405
        assert client.patch(DECKS, json={}, headers=headers).status_code == 405

    def test_single_deck_does_not_allow_post_or_get(self, client, user, headers, make_deck):
        deck_id = make_deck(user["email"])
        assert client.post(deck_url(deck_id), json={"name": "N"}, headers=headers).status_code == 405
        assert client.put(deck_url(deck_id), json={"name": "N"}, headers=headers).status_code == 405

    def test_non_integer_id_is_404(self, client, headers):
        assert client.delete("/api/v1/deck/abc", headers=headers).status_code == 404
