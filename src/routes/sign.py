import re

from flask import Blueprint, Response, jsonify
from sqlalchemy.exc import IntegrityError

from consts import EMAIL_MAX_LENGTH, EMAIL_REGEX, NAME_MAX_LENGTH, PASSWORD_REGEX
from database import db
from models.base import Account
from routes.utils import error_response, get_json_strings
from services.sign import create_hash

sign = Blueprint("sign", __name__)

# TODO: Add a "/api/v1/resetpassword/" endpoint with setup SMTP .env variables.


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
