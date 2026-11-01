import re
from datetime import datetime, timedelta, timezone

from flask import Blueprint, Response, jsonify
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from consts import EMAIL_MAX_LENGTH, EMAIL_REGEX, NAME_MAX_LENGTH, PASSWORD_REGEX
from database import db
from models.base import Account
from models.security import PasswordResetToken
from routes.utils import error_response, get_json_strings
from services.mail import send_reset_password_email
from services.sign import create_hash
from services.token import generate_and_hash_token, hash_token

sign = Blueprint("sign", __name__)

RESET_TOKEN_LIFESPAN = timedelta(minutes=30)


@sign.route("/api/v1/resetpassword/confirm", methods=["POST"])
def confirm_password_reset():
    """
    JSON body: {"token": str, "new_password": str}

    Answers:
        - 200: {"status": "ok"}
        - 400 `InvalidRequest`: body is not a JSON object, or a field is missing/invalid
        - 400 `InvalidPassword`: new password does not meet the security rules
        - 400 `InvalidToken`: unknown, expired or already-used token — deliberately
          indistinguishable, same as /token/create and require_token.
    """
    fields = get_json_strings("token", "new_password")
    if fields is None:
        return error_response(
            "InvalidRequest", "Body must be JSON with token and new_password.", 400
        )

    raw_token = fields["token"].strip()
    new_password = fields["new_password"]

    if not re.fullmatch(PASSWORD_REGEX, new_password):
        return error_response(
            "InvalidPassword", "Password does not meet the security rules.", 400
        )

    reset_token = db.session.get(PasswordResetToken, hash_token(raw_token))
    now = datetime.now(timezone.utc)
    if (
        reset_token is None
        or reset_token.used_at is not None
        or reset_token.expires_at <= now
    ):
        return error_response("InvalidToken", "Invalid, used or expired token.", 400)

    account = db.session.get(Account, reset_token.account_email)
    account.password = create_hash(new_password)
    reset_token.used_at = now

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return error_response("DatabaseError", "Database error.", 500)

    return jsonify({"status": "ok"}), 200


@sign.route("/api/v1/resetpassword", methods=["POST"])
def request_password_reset():
    """
    JSON body: {"email": str}

    Always answers 200 — never reveals whether the email exists (same
    anti-enumeration pattern as /token/create).
    """
    fields = get_json_strings("email")
    if fields is None:
        return error_response("InvalidRequest", "Body must be JSON with email.", 400)

    email = fields["email"].strip().lower()
    account = db.session.get(Account, email)

    if account is not None:
        t_key, t_hash = generate_and_hash_token()
        now = datetime.now(timezone.utc)
        db.session.add(
            PasswordResetToken(
                token_hash=t_hash,
                created_at=now,
                expires_at=now + RESET_TOKEN_LIFESPAN,
                account_email=email,
            )
        )
        db.session.commit()
        try:
            send_reset_password_email(email, t_key)
        except Exception:
            # Best-effort: don't leak SMTP failures to the client, don't roll back the token.
            pass

    return jsonify({"status": "ok"}), 200


def _email_taken() -> Response:
    return error_response("EmailAlreadyUsed", "This email is already registered.", 409)


@sign.route("/api/v1/connexion/signup", methods=["POST"])
def signup():
    """
    Create a new account.

    JSON body: {"email": str, "password": str, "name": str}

    Answers:
        - 201: account created (never returns the password or its hash).
        - 400 `InvalidRequest` / `InvalidEmail` / `InvalidPassword` / `InvalidName`
        - 409 `EmailAlreadyUsed`
    """
    fields = get_json_strings("email", "password", "name")
    if fields is None:
        return error_response(
            "InvalidRequest", "Body must be JSON with email, password and name.", 400
        )

    email = fields["email"].strip().lower()
    password = fields["password"]
    name = fields["name"].strip()

    if len(email) > EMAIL_MAX_LENGTH or not re.fullmatch(EMAIL_REGEX, email):
        return error_response("InvalidEmail", "Invalid email address.", 400)
    if not re.fullmatch(PASSWORD_REGEX, password):
        return error_response(
            "InvalidPassword", "Password does not meet the security rules.", 400
        )
    if not name or len(name) > NAME_MAX_LENGTH:
        return error_response("InvalidName", "Invalid name.", 400)

    if db.session.get(Account, email) is not None:
        return _email_taken()

    db.session.add(Account(email=email, name=name, password=create_hash(password)))
    try:
        db.session.commit()
    except IntegrityError:  # two signups with the same email at the same time
        db.session.rollback()
        return _email_taken()

    return jsonify({"email": email, "name": name}), 201
