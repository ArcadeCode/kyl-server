"""parse_session_card, parse_session_deck and parse_study_session from a dict."""

from datetime import datetime, timedelta, timezone

import pytest

from consts import MAX_CARD_ANSWER_LENGTH, MAX_CARD_QUESTION_LENGTH
from exceptions import (
    InvalidSessionCardData,
    InvalidSessionDeckData,
    InvalidStudySessionData,
)
from models.session import SessionCard
from services.session import parse_session_card, parse_session_deck, parse_study_session

CARD = {
    "question": "1+1 ?",
    "correct_answer": "2",
    "user_answer": "3",
    "is_tolerant": False,
    "position": 0,
}
STUDY = {
    "timestamp": "2026-01-01T12:00:00Z",
    "tolerance_allowed": True,
    "is_tolerance_forced": False,
}


def refused(func, data, error=Exception):
    with pytest.raises(error) as info:
        func(data)
    return info.value


# --------------------------------------------------------------------------- SessionCard


class TestParseSessionCard:
    def test_valid_data_gives_a_session_card(self):
        card = parse_session_card(CARD)
        assert isinstance(card, SessionCard)
        assert (
            card.question, card.correct_answer, card.user_answer, card.is_tolerant, card.position
        ) == ("1+1 ?", "2", "3", False, 0)

    def test_extra_fields_are_ignored(self):
        card = parse_session_card({**CARD, "session_card_id": 99, "session_deck_id": 99})
        assert card.session_card_id is None and card.session_deck_id is None

    @pytest.mark.parametrize("missing", list(CARD))
    def test_missing_field(self, missing):
        error = refused(
            parse_session_card,
            {k: v for k, v in CARD.items() if k != missing},
            InvalidSessionCardData,
        )
        assert error.field == missing

    @pytest.mark.parametrize(
        "field, value",
        [
            ("question", 1), ("question", None), ("question", ["a"]),
            ("correct_answer", 1), ("correct_answer", None), ("correct_answer", {"a": 1}),
            ("user_answer", 1), ("user_answer", None), ("user_answer", ["a"]),
            ("is_tolerant", "true"), ("is_tolerant", 1), ("is_tolerant", None),
            ("position", "1"), ("position", 1.5), ("position", None), ("position", True),
        ],
    )
    def test_wrong_type(self, field, value):
        error = refused(parse_session_card, {**CARD, field: value}, InvalidSessionCardData)
        assert error.field == field

    @pytest.mark.parametrize("position", [-1, -100])
    def test_negative_position_is_refused(self, position):
        error = refused(parse_session_card, {**CARD, "position": position}, InvalidSessionCardData)
        assert error.field == "position"

    def test_position_zero_is_accepted(self):
        assert parse_session_card({**CARD, "position": 0}).position == 0

    @pytest.mark.parametrize(
        "field, limit",
        [
            ("question", MAX_CARD_QUESTION_LENGTH),
            ("correct_answer", MAX_CARD_ANSWER_LENGTH),
            ("user_answer", MAX_CARD_ANSWER_LENGTH),
        ],
    )
    def test_text_limits_are_inclusive(self, field, limit):
        assert parse_session_card({**CARD, field: "x" * limit})
        error = refused(
            parse_session_card, {**CARD, field: "x" * (limit + 1)}, InvalidSessionCardData
        )
        assert error.field == field

    def test_empty_user_answer_is_accepted(self):
        """A skipped question has no answer."""
        assert parse_session_card({**CARD, "user_answer": ""}).user_answer == ""

    def test_limits_are_independent(self):
        data = {
            **CARD,
            "question": "q" * MAX_CARD_QUESTION_LENGTH,
            "correct_answer": "a" * MAX_CARD_ANSWER_LENGTH,
            "user_answer": "u" * MAX_CARD_ANSWER_LENGTH,
        }
        assert parse_session_card(data)


# --------------------------------------------------------------------------- SessionDeck


class TestParseSessionDeck:
    def test_valid_data(self):
        assert parse_session_deck({"name": "Maths", "description": "Chap. 1"}) == {
            "name": "Maths",
            "description": "Chap. 1",
        }

    def test_description_is_optional_and_defaults_to_empty(self):
        assert parse_session_deck({"name": "Maths"}) == {"name": "Maths", "description": ""}

    def test_name_is_trimmed(self):
        assert parse_session_deck({"name": "  Maths  "})["name"] == "Maths"

    def test_extra_fields_are_dropped(self):
        data = {"name": "M", "session_deck_id": 3, "study_session_id": 4, "owner_email": "x@y.fr"}
        assert set(parse_session_deck(data)) == {"name", "description"}

    def test_missing_name(self):
        error = refused(parse_session_deck, {"description": "d"}, InvalidSessionDeckData)
        assert error.field == "name"

    @pytest.mark.parametrize("name", ["", "   ", "\n\t"])
    def test_blank_name(self, name):
        assert refused(parse_session_deck, {"name": name}, InvalidSessionDeckData).field == "name"

    @pytest.mark.parametrize("value", [1, None, ["a"], {"a": 1}, True])
    def test_name_wrong_type(self, value):
        assert refused(parse_session_deck, {"name": value}, InvalidSessionDeckData).field == "name"

    @pytest.mark.parametrize("value", [1, None, ["a"], {"a": 1}, False])
    def test_description_wrong_type(self, value):
        error = refused(
            parse_session_deck, {"name": "M", "description": value}, InvalidSessionDeckData
        )
        assert error.field == "description"

    def test_name_uniqueness_is_not_the_service_job(self):
        """Unlike Deck, several session decks may share a name: the service never checks."""
        assert parse_session_deck({"name": "Maths"}) == parse_session_deck({"name": "Maths"})


# --------------------------------------------------------------------------- StudySession


class TestParseStudySession:
    def test_valid_data(self):
        result = parse_study_session(STUDY)
        assert set(result) == {"timestamp", "tolerance_allowed", "is_tolerance_forced"}
        assert result["timestamp"] == datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        assert result["tolerance_allowed"] is True
        assert result["is_tolerance_forced"] is False

    def test_timestamp_is_a_timezone_aware_datetime(self):
        assert parse_study_session(STUDY)["timestamp"].tzinfo is not None

    def test_offset_is_converted_to_the_same_instant(self):
        result = parse_study_session({**STUDY, "timestamp": "2026-01-01T14:00:00+02:00"})
        assert result["timestamp"] == datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        assert result["timestamp"].utcoffset() == timedelta(0)

    def test_naive_timestamp_is_considered_utc(self):
        result = parse_study_session({**STUDY, "timestamp": "2026-01-01T12:00:00"})
        assert result["timestamp"] == datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    @pytest.mark.parametrize("value", ["hier", "", "2026-13-45T00:00:00", 123, None, ["x"], True])
    def test_unreadable_timestamp(self, value):
        error = refused(parse_study_session, {**STUDY, "timestamp": value}, InvalidStudySessionData)
        assert error.field == "timestamp"

    @pytest.mark.parametrize("missing", list(STUDY))
    def test_missing_field_is_a_validation_error_not_a_keyerror(self, missing):
        error = refused(
            parse_study_session,
            {k: v for k, v in STUDY.items() if k != missing},
            InvalidStudySessionData,
        )
        assert error.field == missing

    @pytest.mark.parametrize("tolerance_allowed", [True, False])
    @pytest.mark.parametrize("is_tolerance_forced", [True, False])
    def test_every_boolean_combination_is_accepted(self, tolerance_allowed, is_tolerance_forced):
        """False must not be mistaken for 'empty'."""
        result = parse_study_session(
            {**STUDY, "tolerance_allowed": tolerance_allowed, "is_tolerance_forced": is_tolerance_forced}
        )
        assert result["tolerance_allowed"] is tolerance_allowed
        assert result["is_tolerance_forced"] is is_tolerance_forced

    @pytest.mark.parametrize("field", ["tolerance_allowed", "is_tolerance_forced"])
    @pytest.mark.parametrize("value", ["true", 1, 0, None, [True]])
    def test_boolean_wrong_type(self, field, value):
        error = refused(parse_study_session, {**STUDY, field: value}, InvalidStudySessionData)
        assert error.field == field

    def test_extra_fields_are_dropped(self):
        result = parse_study_session({**STUDY, "session_id": 5, "owner_email": "x@y.fr"})
        assert set(result) == {"timestamp", "tolerance_allowed", "is_tolerance_forced"}

    @pytest.mark.parametrize(
        "data",
        [
            {},
            {**STUDY, "timestamp": "nope"},
            {**STUDY, "tolerance_allowed": "x"},
            {**STUDY, "is_tolerance_forced": None},
        ],
    )
    def test_every_error_is_an_invalid_study_session_data(self, data):
        refused(parse_study_session, data, InvalidStudySessionData)
