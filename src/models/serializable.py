from datetime import datetime
from typing import Any


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


class SerializableMixin:
    __json_fields__: tuple[str, ...] = ()  # Whitelist

    def to_dict(self, relations: tuple[str, ...] = ()) -> dict[str, Any]:
        """
        relations: names of relations to include (nested). Relations are
        serialized only when explicitly requested, which avoids infinite loops
        (Deck -> cards -> deck -> ...).
        """
        data = {
            field: _jsonable(getattr(self, field)) for field in self.__json_fields__
        }

        for name in relations:
            value = getattr(self, name)
            if value is None:
                data[name] = None
            elif isinstance(value, list):
                data[name] = [item.to_dict() for item in value]
            else:
                data[name] = value.to_dict()

        return data
