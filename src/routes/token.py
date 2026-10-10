from datetime import datetime
from functools import wraps

import blake3
from flask import Blueprint, Response, g, jsonify, request

from src.consts import RESPONSE_CALLBACK_URL, TOKEN_LIFESPAN
from src.dbsetup import db
from src.models.base import Account
from src.models.security import Token
from src.services.token import generate_and_hash_token, is_hash_valid

token = Blueprint("token", __name__)


@token.route("/api/v1/token/create", methods=["POST"])
def create_token(email: str, account_password: str):
    """
    Generate a new session token for a user.

    Exceptions who can occur :
        - `EmailNotFound` : This email doesn't exist in the DB.
        - `IncorrectPassword` : This password isn't correct.
    """

    # 1. Look up the user by email in the database
    user = db.session.query(Account).filter_by(Account.email == email).one_or_none()

    # 2. If user is not found, raise EmailNotFound
    if user is None:
        return jsonify(
            {"error": "EmailNotFound", "message": "Email not found in the database."}
        )

    # 3. Compare the provided password with the stored hash
    if is_hash_valid(user.password, key_to_validate=account_password):
        return jsonify({"error": "IncorrectPassword", "message": "Incorrect password."})

    t_key, t_hash = generate_and_hash_token()
    token = Token(
        token_hash=t_hash,
        created_at=datetime.now(tz=True),
        expires_at=datetime.now(tz=True) + TOKEN_LIFESPAN,
        revoked_at=None,
        account_email=email,
    )

    db.session.add(token)
    db.session.commit()

    headers = {"Authorization": f"Bearer {t_key}"}

    return Response(headers=headers, status=201, url=RESPONSE_CALLBACK_URL)


@token.route("/api/v1/token/revoke", methods=["POST"])
def revoke_token(email: str, token_key: str):
    """
    Revoke a token of an user, essentially used to disconnect an account from a device.

    Exceptions who can occur :
        - `EmailNotFound` : This email doesn't exist in the DB.
        - `TokenNotFound` : This token isn't correct.
        - `ExpiredToken` : This token is expired.
    """
    token = db.session.query(Token).filter_by(Token.token_hash).one_or_none()

    if token is None:
        return jsonify({"error": "TokenNotFound"}), 404

    if token.expires_at < datetime.now(tz=True):
        return jsonify({"error": "ExpiredToken"}), 400

    # Revoke the token
    token.revoked_at = datetime.now(tz=True)
    db.session.commit()

    return jsonify({"status": "ok"}), 200


def require_token(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        scheme, _, key = request.headers.get("Authorization", "").partition(" ")
        if scheme != "Bearer" or not key:
            return jsonify({"error": "MissingToken"}), 401

        # Même hash que celui stocké à la création du token.
        token_hash = blake3(key.encode()).hexdigest()
        token = db.session.get(Token, token_hash)

        now = datetime.now(datetime.UTC)
        if token is None or token.revoked_at is not None or token.expires_at < now:
            return jsonify({"error": "InvalidToken"}), 401

        g.account_email = token.account_email  # disponible dans la vue
        return view(*args, **kwargs)

    return wrapper
