import hmac
import secrets

from blake3 import blake3


def hash_token(key: str) -> str:
    """BLAKE3-256 hex digest (64 chars) of a raw token, as stored in `Token.token_hash`."""
    return blake3(key.encode("utf-8")).hexdigest()


def generate_and_hash_token(length: int = 32) -> tuple[str, str]:
    """
    Generate a random token.

    Args:
        length (int): Number of random bytes used to build the token.

    Returns:
        t_key, t_hash (str, str): The raw token (given once to the client) and
        its hex hash (the only thing stored in DB).
    """
    t_key = secrets.token_urlsafe(length)
    return t_key, hash_token(t_key)


def is_hash_valid(t_hash: str, key_to_validate: str) -> bool:
    """
    Check that a given raw key produces the given hash.

    The comparison is done in constant time.

    Args:
        t_hash (str): Trusted hex hash (from the DB).
        key_to_validate (str): Raw key given by the emitter.
    """
    return hmac.compare_digest(t_hash, hash_token(key_to_validate))
