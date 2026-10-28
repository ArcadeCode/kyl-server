"""parse_deck (creation) and parse_deck_update (PATCH: partial) from a dict."""

import pytest

from exceptions import InvalidDeckData
from services.deck import parse_deck, parse_deck_update


def refused(func, data) -> InvalidDeckData:
    with pytest.raises(InvalidDeckData) as info:
        func(data)
    return info.value


class TestParseDeck:
    def test_valid_data(self):
        assert parse_deck({"name": "Maths", "description": "Chap. 1"}) == {
            "name": "Maths",
            "description": "Chap. 1",
        }

    def test_description_is_optional_and_defaults_to_empty(self):
        assert parse_deck({"name": "Maths"}) == {"name": "Maths", "description": ""}

    def test_name_is_trimmed(self):
        assert parse_deck({"name": "  Maths  "})["name"] == "Maths"

    def test_extra_fields_are_dropped(self):
        assert set(parse_deck({"name": "M", "id": 3, "owner_email": "x@y.fr"})) == {"name", "description"}

    def test_missing_name(self):
        assert refused(parse_deck, {"description": "d"}).field == "name"

    @pytest.mark.parametrize("name", ["", "   ", "\n\t"])
    def test_blank_name(self, name):
        assert refused(parse_deck, {"name": name}).field == "name"

    @pytest.mark.parametrize("value", [1, None, ["a"], {"a": 1}, True])
    def test_name_wrong_type(self, value):
        assert refused(parse_deck, {"name": value}).field == "name"

    @pytest.mark.parametrize("value", [1, None, ["a"], {"a": 1}, False])
    def test_description_wrong_type(self, value):
        assert refused(parse_deck, {"name": "M", "description": value}).field == "description"


class TestParseDeckUpdate:
    def test_only_the_given_fields(self):
        assert parse_deck_update({"description": "new"}) == {"description": "new"}
        assert parse_deck_update({"name": " New "}) == {"name": "New"}

    def test_both_fields(self):
        assert parse_deck_update({"name": "N", "description": "D"}) == {"name": "N", "description": "D"}

    def test_empty_update_is_refused(self):
        assert refused(parse_deck_update, {}).field == "body"

    def test_only_unknown_fields_is_refused(self):
        assert refused(parse_deck_update, {"id": 1}).field == "body"

    def test_blank_name_is_refused(self):
        assert refused(parse_deck_update, {"name": "  "}).field == "name"

    @pytest.mark.parametrize("field", ["name", "description"])
    @pytest.mark.parametrize("value", [1, None, ["a"]])
    def test_wrong_type(self, field, value):
        assert refused(parse_deck_update, {field: value}).field == field

    def test_empty_description_is_allowed(self):
        assert parse_deck_update({"description": ""}) == {"description": ""}
