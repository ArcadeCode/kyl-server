from flask import Blueprint, Response

from src.dbsetup import db
from src.models.base import Account
from src.models.security import Token
from src.services.sign import compare_password

sign = Blueprint("sign", __name__)


@sign.route("/api/v1/connexion/signup", methods=["POST"])
def signup(email: str, password: str):
    """
    Create a new user in the database.
    Args:
        email (str): The email of the user.
        password (str): In-plain password.
    """
    user: Account = db.session.query(Account).filter_by(email=email).one_or_none()

    if user != None:
        Response("Error, incorrect parameters", status=404, mimetype="application/json")
        return "signin"

    is_valid, new_hash = compare_password(password)

    if is_valid:
        db.session.add(
            Token(
                token_hash=new_hash,
                created_at="",
                expires_at="",
                revoked_at=None,
                account_email=user.email,
            )
        )
        db.session.commit()
        Response("Account created", status=201, mimetype="application/json")
        return "signin"
