from exceptions import InvalidCardData
from models.base import Card

_REQUIRED_PARAMS = ("question", "answer", "is_tolerant", "position")


def parse_card(data: dict) -> Card:
    """
    Parser for JSON requests with Card

    Args:
        card (dict): JSON representation of a Card

    Returns:
        (Card) Card has been parsed
    """

    for param in _REQUIRED_PARAMS:
        if param not in data:
            print(
                f"Error when parsing cards, field: {param} not found in Card : {data}"
            )
            raise InvalidCardData(param, "field is required")

    if not isinstance(data["question"], str):
        raise InvalidCardData("question", "must be a string")
    if not isinstance(data["answer"], str):
        raise InvalidCardData("answer", "must be a string")
    if not isinstance(data["is_tolerant"], bool):
        raise InvalidCardData("is_tolerant", "must be a boolean")
    if not isinstance(data["position"], int):
        raise InvalidCardData("position", "must be an integer")

    return Card(
        question=data["question"],
        answer=data["answer"],
        is_tolerant=data["is_tolerant"],
        position=data["position"],
    )
