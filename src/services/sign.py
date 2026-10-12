from functools import lru_cache

import bcrypt

from consts import PASSWORD_MAX_LENGTH


def create_hash(password: str) -> str:
    """
    Generate a bcrypt hash from a password.

    Args:
        password (str): The in-plain password that needs to be hashed.

    Returns:
        (str): The bcrypt hash (algorithm, cost and salt are embedded in it).

    Raises:
        ValueError: If the password is longer than 72 bytes (bcrypt limit).
    """
    raw = password.encode("utf-8")
    if len(raw) > PASSWORD_MAX_LENGTH:
        raise ValueError(f"Password longer than {PASSWORD_MAX_LENGTH} bytes")
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("ascii")


def compare_password(password: str, password_hash: str) -> tuple[bool, str | None]:
    """
    Compare a password with its hash stored in DB.

    Args:
        password (str): The password given, that needs to be validated.
        password_hash (str): The bcrypt hash from the database.

    Returns:
        is_valid, new_hash (bool, str | None): Whether the password is valid and,
        only if it is, a fresh hash (new salt) to store in place of the old one.
        `new_hash` is None when the password is not valid.
    """
    raw = password.encode("utf-8")
    if len(raw) > PASSWORD_MAX_LENGTH:
        return False, None

    try:
        is_valid = bcrypt.checkpw(raw, password_hash.encode("utf-8"))
    except ValueError:  # malformed hash
        return False, None

    if not is_valid:
        return False, None
    return True, create_hash(password)


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return create_hash("not-a-real-password-1")


def fake_verify(password: str) -> None:
    """
    Spend the same time as a real verification. Used when the account does
    not exist, so that response time does not reveal which emails are registered.
    """
    compare_password(password, _dummy_hash())
