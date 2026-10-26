from consts import MAX_CARD_ANSWER_LENGTH, MAX_CARD_QUESTION_LENGTH
from exceptions import InvalidCardData
from models.base import Card

_REQUIRED_PARAMS = ("question", "answer", "is_tolerant", "position")
_MAX_LENGTHS = {
    "question": MAX_CARD_QUESTION_LENGTH,
    "answer": MAX_CARD_ANSWER_LENGTH,
}


def _validate_field(field: str, value: object) -> None:
    """Raise InvalidCardData if `value` is not acceptable for the card field `field`."""
    if field in _MAX_LENGTHS:
        if not isinstance(value, str):
            raise InvalidCardData(field, "must be a string")
        if len(value) > _MAX_LENGTHS[field]:
            raise InvalidCardData(
                field, f"must be at most {_MAX_LENGTHS[field]} characters"
            )
    elif field == "is_tolerant":
        if not isinstance(value, bool):
            raise InvalidCardData(field, "must be a boolean")
    elif field == "position":
        # bool is a subclass of int: True/False must not pass as a position.
        if not isinstance(value, int) or isinstance(value, bool):
            raise InvalidCardData(field, "must be an integer")
        if value < 0:
            raise InvalidCardData(field, "must be greater than or equal to 0")


def parse_card(data: dict) -> Card:
    """
    Parse and validate the JSON representation of a new Card.

    Every field of `_REQUIRED_PARAMS` is required. Unknown fields (card_id,
    deck_id...) are ignored: the client does not choose them.

    Args:
        data (dict): JSON representation of a Card.

    Returns:
        (Card) A new, not yet persisted, Card.

    Raises:
        InvalidCardData: A field is missing or invalid.
    """
    for param in _REQUIRED_PARAMS:
        if param not in data:
            raise InvalidCardData(param, "field is required")

    for param in _REQUIRED_PARAMS:
        _validate_field(param, data[param])

    return Card(
        question=data["question"],
        answer=data["answer"],
        is_tolerant=data["is_tolerant"],
        position=data["position"],
    )


def parse_card_update(data: dict) -> dict:
    """
    Parse and validate a partial update of a Card (PATCH).

    Args:
        data (dict): Any subset of `_REQUIRED_PARAMS`. Unknown fields are dropped.

    Returns:
        (dict) Only the validated fields that were given.

    Raises:
        InvalidCardData: No known field was given, or one of them is invalid.
    """
    changes = {param: data[param] for param in _REQUIRED_PARAMS if param in data}
    if not changes:
        raise InvalidCardData(
            "body", f"at least one of {', '.join(_REQUIRED_PARAMS)} is required"
        )

    for field, value in changes.items():
        _validate_field(field, value)
    return changes
