from datetime import datetime, timezone
from functools import wraps

from flask import g, request

from database import db
from models.security import Token
from routes.utils import error_response
from services.token import hash_token

_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}


def _as_utc(value: datetime) -> datetime:
    # PostgreSQL returns aware datetimes; be tolerant of naive ones (e.g. SQLite).
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def require_token(view):
    """
    Protect a view with a `Authorization: Bearer <token>` header.

    On success, `g.account_email` and `g.token` (the `Token` row) are available
    in the view. Every failure answers 401 with a JSON error.
    """

    @wraps(view)
    def wrapper(*args, **kwargs):
        scheme, _, key = request.headers.get("Authorization", "").partition(" ")
        key = key.strip()
        if scheme.lower() != "bearer" or not key:
            return error_response(
                "MissingToken", "Missing bearer token.", 401, _UNAUTHORIZED_HEADERS
            )

        # Same hash as the one stored at token creation.
        token = db.session.get(Token, hash_token(key))
        now = datetime.now(timezone.utc)
        if (
            token is None
            or token.revoked_at is not None
            or _as_utc(token.expires_at) <= now
        ):
            return error_response(
                "InvalidToken", "Invalid, revoked or expired token.", 401,
                _UNAUTHORIZED_HEADERS,
            )

        g.account_email = token.account_email
        g.token = token
        return view(*args, **kwargs)

    return wrapper
