from datetime import datetime

from consts import MAX_CARD_ANSWER_LENGTH, MAX_CARD_QUESTION_LENGTH
from exceptions import (
    InvalidSessionCardData,
    InvalidSessionDeckData,
    InvalidStudySessionData,
)
from models.session import SessionCard

_CARD_REQUIRED_PARAMS = (
    "question",
    "correct_answer",
    "user_answer",
    "is_tolerant",
    "position",
)
_MAX_LENGTHS = {
    "question": MAX_CARD_QUESTION_LENGTH,
    "correct_answer": MAX_CARD_ANSWER_LENGTH,
    "user_answer": MAX_CARD_ANSWER_LENGTH,
}


def _validate_session_card_field(field: str, value: object) -> None:
    """Raise InvalidSessionCardData if `value` is not acceptable for the card field `field`."""
    if field in _MAX_LENGTHS:
        if not isinstance(value, str):
            raise InvalidSessionCardData(field, "must be a string")
        if len(value) > _MAX_LENGTHS[field]:
            raise InvalidSessionCardData(
                field, f"must be at most {_MAX_LENGTHS[field]} characters"
            )
    elif field == "is_tolerant":
        if not isinstance(value, bool):
            raise InvalidSessionCardData(field, "must be a boolean")
    elif field == "position":
        # bool is a subclass of int: True/False must not pass as a position.
        if not isinstance(value, int) or isinstance(value, bool):
            raise InvalidSessionCardData(field, "must be an integer")
        if value < 0:
            raise InvalidSessionCardData(field, "must be greater than or equal to 0")


def _validate_session_deck_field(field: str, value: object) -> str:
    """Return the cleaned value of a session deck field, or raise InvalidSessionDeckData."""
    if not isinstance(value, str):
        raise InvalidSessionDeckData(field, "must be a string")
    if field == "name":
        value = value.strip()
        if not value:
            raise InvalidSessionDeckData(field, "must not be empty")
    return value


def _validate_study_session_field(field: str, value: object) -> str:
    if field == "timestamp" and not isinstance(value, datetime):
        raise InvalidStudySessionData(field, "must be a timestamp")
    if field == "tolerance_allowed" and not isinstance(value, bool):
        raise InvalidStudySessionData(field, "must be a boolean")
    if field == "is_tolerance_forced" and not isinstance(value, bool):
        raise InvalidStudySessionData(field, "must be a boolean")

    return value


def parse_session_card(data: dict) -> SessionCard:
    """
    Parse and validate the JSON representation of a new SessionCard.

    Every field of `_CARD_REQUIRED_PARAMS` is required. Unknown fields (card_id,
    deck_id...) are ignored: the client does not choose them.

    Args:
        data (dict): JSON representation of a Card.

    Returns:
        (SessionCard) A new, not yet persisted, SessionCard.

    Raises:
        InvalidSessionCardData: A field is missing or invalid.
    """
    for param in _CARD_REQUIRED_PARAMS:
        if param not in data:
            raise InvalidSessionCardData(param, "field is required")

    for param in _CARD_REQUIRED_PARAMS:
        _validate_session_card_field(param, data[param])

    return SessionCard(
        question=data["question"],
        correct_answer=data["correct_answer"],
        user_answer=data["user_answer"],
        is_tolerant=data["is_tolerant"],
        position=data["position"],
    )


def parse_session_deck(data: dict) -> dict:
    """
    Parse and validate the JSON representation of a new SessionDeck.

    `name` is required (trimmed, non-empty). `description` is optional and
    defaults to "". Unknown fields (id, owner_email...) are dropped: the client
    does not choose them.

    Returns:
        (dict) {"name": str, "description": str}, ready for `Deck(**...)`.

    Raises:
        InvalidSessionDeckData: `name` is missing, or a field is invalid.
    """
    if "name" not in data:
        raise InvalidSessionDeckData("name", "field is required")

    return {
        "name": _validate_session_deck_field("name", data["name"]),
        "description": _validate_session_deck_field(
            "description", data.get("description", "")
        ),
    }


def parse_study_session(data: dict) -> dict:
    """
    Parse and validate the JSON representation of a new StudySession.

    `timestamp` is required (datetime, non-empty),
    `tolerance_allowed` is required (bool, non-empty),
    `is_tolerance_forced` is required (bool, non-empty).
    Unknown fields (id, owner_email...) are dropped: the client
    does not choose them.

    Returns:
        (dict) {
            "timestamp": datetime,
            "tolerance_allowed": bool,
            "is_tolerance_forced": bool
            }, ready for `Deck(**...)`.

    Raises:
        InvalidStudySessionData: `name` is missing, or a field is invalid.
    """
    for field, value in zip(data):
        if field == "timestamp" and not value:
            raise InvalidStudySessionData(field, "must not be empty")
        if field == "tolerance_allowed" and not value:
            raise InvalidSessionDeckData(field, "must not be empty")
        if field == "is_tolerance_forced" and not value:
            raise InvalidSessionDeckData(field, "must not be empty")

    return {
        "timestamp": _validate_study_session_field("timestamp", data["timestamp"]),
        "tolerance_allowed": _validate_study_session_field(
            "tolerance_allowed", data["tolerance_allowed"]
        ),
        "is_tolerance_forced": _validate_study_session_field(
            "is_tolerance_forced", data["is_tolerance_forced"]
        ),
    }
