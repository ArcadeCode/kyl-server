from datetime import datetime, timezone

from flask import Blueprint, g, jsonify

from auth import require_token
from consts import TOKEN_LIFESPAN
from database import db
from models.base import Account
from models.security import Token
from routes.utils import error_response, get_json_strings
from services.sign import compare_password, fake_verify
from services.token import generate_and_hash_token

token = Blueprint("token", __name__)


@token.route("/api/v1/token/create", methods=["POST"])
def create_token():
    """
    Log in: generate a new token (one per device) for an account.

    JSON body: {"email": str, "password": str}

    Answers:
        - 201: {"token": <raw token, shown only once>, "expires_at": <ISO 8601>}
        - 400 `InvalidRequest`
        - 401 `InvalidCredentials`: unknown email and wrong password are
          deliberately indistinguishable.

    Tokens last TOKEN_LIFESPAN and cannot be refreshed: log in again after that.
    """
    fields = get_json_strings("email", "password")
    if fields is None:
        return error_response(
            "InvalidRequest", "Body must be JSON with email and password.", 400
        )

    email = fields["email"].strip().lower()
    password = fields["password"]

    account = db.session.get(Account, email)
    if account is None:
        fake_verify(password)
        is_valid, new_hash = False, None
    else:
        is_valid, new_hash = compare_password(password, account.password)

    if not is_valid:
        return error_response("InvalidCredentials", "Incorrect email or password.", 401)

    t_key, t_hash = generate_and_hash_token()
    now = datetime.now(timezone.utc)
    expires_at = now + TOKEN_LIFESPAN

    db.session.add(
        Token(
            token_hash=t_hash,
            created_at=now,
            expires_at=expires_at,
            revoked_at=None,
            account_email=account.email,
        )
    )
    account.password = new_hash  # fresh salt on every successful login
    db.session.commit()

    response = jsonify({"token": t_key, "expires_at": expires_at.isoformat()})
    response.status_code = 201
    response.headers["Cache-Control"] = "no-store"
    return response


@token.route("/api/v1/token/revoke", methods=["POST"])
@require_token
def revoke_token():
    """
    Log out: revoke the token used to make this very request.

    Answers:
        - 200: {"status": "ok"}
        - 401: missing / invalid / already revoked / expired token (see require_token)
    """
    g.token.revoked_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({"status": "ok"}), 200
