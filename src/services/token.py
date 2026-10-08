from blake3 import blake3


def generate_and_hash_token(length: int = 32) -> (str, bytes):
    """
    Generate a random token

    Args:
        length (int): The length of the token to generate.

    Returns:
        t_key, t_hash (str, bytes) : Tuple with the hash and the hashed result.
    """
    import secrets

    t_key = secrets.token_urlsafe(length)
    t_hash = blake3(t_key.encode()).digest()

    return t_key, t_hash


def is_hash_valid(t_hash: bytes, key_to_validate: str) -> bool:
    """
    Check if an given hash key generate the correct hash.

    If the emitter key_to_validate hash return the same hash has the receiver t_hash, the hash is valid.

    Args:
        t_hash (bytes): Ensured valid hash.
        key_to_validate (str): Key gave by the emitter.
    """
    return t_hash == blake3(bytes(key_to_validate)).digest()
