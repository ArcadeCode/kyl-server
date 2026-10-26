from exceptions import InvalidDeckData

_FIELDS = ("name", "description")


def _validate_field(field: str, value: object) -> str:
    """Return the cleaned value of a deck field, or raise InvalidDeckData."""
    if not isinstance(value, str):
        raise InvalidDeckData(field, "must be a string")
    if field == "name":
        value = value.strip()
        if not value:
            raise InvalidDeckData(field, "must not be empty")
    return value


def parse_deck(data: dict) -> dict:
    """
    Parse and validate the JSON representation of a new Deck.

    `name` is required (trimmed, non-empty). `description` is optional and
    defaults to "". Unknown fields (id, owner_email...) are dropped: the client
    does not choose them.

    Returns:
        (dict) {"name": str, "description": str}, ready for `Deck(**...)`.

    Raises:
        InvalidDeckData: `name` is missing, or a field is invalid.
    """
    if "name" not in data:
        raise InvalidDeckData("name", "field is required")

    return {
        "name": _validate_field("name", data["name"]),
        "description": _validate_field("description", data.get("description", "")),
    }


def parse_deck_update(data: dict) -> dict:
    """
    Parse and validate a partial update of a Deck (PATCH).

    Args:
        data (dict): `name` and/or `description`. Unknown fields are dropped.

    Returns:
        (dict) Only the validated fields that were given.

    Raises:
        InvalidDeckData: No known field was given, or one of them is invalid.
    """
    changes = {field: data[field] for field in _FIELDS if field in data}
    if not changes:
        raise InvalidDeckData("body", f"at least one of {', '.join(_FIELDS)} is required")

    return {field: _validate_field(field, value) for field, value in changes.items()}
