import bcrypt


def create_hash(password: str) -> bytes:
    """
    Generate an hash from a password

    Args:
        password (str): The in-plain password who need to be hashed.

    Returns:
        (bytes): The new hash
    """
    # converting password to array of bytes
    password_in_bytes = password.encode("utf-8")
    # generating the salt
    salt = bcrypt.gensalt()
    # Hashing the password
    return bcrypt.hashpw(password_in_bytes, salt)


def compare_password(password: str, hash: bytes) -> (bool, bytes):
    """
    Compare a password with is hash on DB

    Args:
        password (str): The password gave who need to be validate.
        hash (bytes): The hash from the database.

    Returns:
        is_valid, new_hash (str, bytes) : Tuple who represent if the password is valid and return the new Bcrypt hash.
    """
    is_valid: bool = bcrypt.checkpw(password, hashed_password=hash)

    if is_valid:
        # The password is valid, so we refresh the salt.
        return is_valid, create_hash(password)
    else:
        return is_valid, 0b0
