"""parse_card (creation: every field required) and parse_card_update (PATCH: partial)."""

import pytest

from consts import MAX_CARD_ANSWER_LENGTH, MAX_CARD_QUESTION_LENGTH
from exceptions import InvalidCardData
from models.base import Card
from services.card import parse_card, parse_card_update

VALID = {"question": "1+1 ?", "answer": "2", "is_tolerant": False, "position": 0}


def refused(func, data) -> InvalidCardData:
    with pytest.raises(InvalidCardData) as info:
        func(data)
    return info.value


class TestParseCard:
    def test_valid_data_gives_a_card(self):
        card = parse_card(VALID)
        assert isinstance(card, Card)
        assert (card.question, card.answer, card.is_tolerant, card.position) == ("1+1 ?", "2", False, 0)

    def test_extra_fields_are_ignored(self):
        card = parse_card({**VALID, "card_id": 99, "deck_id": 99})
        assert card.card_id is None and card.deck_id is None

    @pytest.mark.parametrize("missing", ["question", "answer", "is_tolerant", "position"])
    def test_missing_field(self, missing):
        error = refused(parse_card, {k: v for k, v in VALID.items() if k != missing})
        assert error.field == missing

    @pytest.mark.parametrize(
        "field, value",
        [
            ("question", 1), ("question", None), ("question", ["a"]),
            ("answer", 1), ("answer", None), ("answer", {"a": 1}),
            ("is_tolerant", "true"), ("is_tolerant", 1), ("is_tolerant", None),
            ("position", "1"), ("position", 1.5), ("position", None), ("position", True),
        ],
    )
    def test_wrong_type(self, field, value):
        assert refused(parse_card, {**VALID, field: value}).field == field

    @pytest.mark.parametrize("position", [-1, -100])
    def test_negative_position_is_refused(self, position):
        assert refused(parse_card, {**VALID, "position": position}).field == "position"

    def test_position_zero_is_accepted(self):
        assert parse_card({**VALID, "position": 0}).position == 0

    def test_question_at_the_limit_is_accepted(self):
        assert parse_card({**VALID, "question": "q" * MAX_CARD_QUESTION_LENGTH})

    def test_question_over_the_limit_is_refused(self):
        error = refused(parse_card, {**VALID, "question": "q" * (MAX_CARD_QUESTION_LENGTH + 1)})
        assert error.field == "question"

    def test_answer_at_the_limit_is_accepted(self):
        assert parse_card({**VALID, "answer": "a" * MAX_CARD_ANSWER_LENGTH})

    def test_answer_over_the_limit_is_refused(self):
        error = refused(parse_card, {**VALID, "answer": "a" * (MAX_CARD_ANSWER_LENGTH + 1)})
        assert error.field == "answer"

    def test_limits_are_independent(self):
        """A long answer is not refused because of the question limit, and vice versa."""
        assert MAX_CARD_QUESTION_LENGTH > 0 and MAX_CARD_ANSWER_LENGTH > 0
        assert parse_card({**VALID, "question": "q" * MAX_CARD_QUESTION_LENGTH, "answer": "a"})
        assert parse_card({**VALID, "question": "q", "answer": "a" * MAX_CARD_ANSWER_LENGTH})


class TestParseCardUpdate:
    def test_returns_only_the_given_fields(self):
        assert parse_card_update({"answer": "3"}) == {"answer": "3"}

    def test_all_fields(self):
        assert parse_card_update(VALID) == VALID

    def test_unknown_fields_are_dropped(self):
        assert parse_card_update({"answer": "3", "card_id": 5, "deck_id": 9}) == {"answer": "3"}

    def test_empty_update_is_refused(self):
        assert refused(parse_card_update, {}).field == "body"

    def test_only_unknown_fields_is_refused(self):
        assert refused(parse_card_update, {"deck_id": 9}).field == "body"

    @pytest.mark.parametrize(
        "field, value",
        [
            ("question", 1), ("answer", None), ("is_tolerant", "no"),
            ("position", "1"), ("position", True), ("position", -1),
        ],
    )
    def test_invalid_value(self, field, value):
        assert refused(parse_card_update, {field: value}).field == field

    def test_question_over_the_limit_is_refused(self):
        error = refused(parse_card_update, {"question": "q" * (MAX_CARD_QUESTION_LENGTH + 1)})
        assert error.field == "question"

    def test_answer_over_the_limit_is_refused(self):
        error = refused(parse_card_update, {"answer": "a" * (MAX_CARD_ANSWER_LENGTH + 1)})
        assert error.field == "answer"

    def test_limits_are_inclusive(self):
        data = {"question": "q" * MAX_CARD_QUESTION_LENGTH, "answer": "a" * MAX_CARD_ANSWER_LENGTH}
        assert parse_card_update(data) == data
