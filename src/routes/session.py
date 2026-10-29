from flask import Blueprint, g, jsonify, request
from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError

from auth import require_token
from consts import MAX_DECK_BY_USER, MAX_SESSION_BY_USER, MAX_STUDY_SESSIONS_PER_DAY
from database import db
from exceptions import InvalidDeckData
from models.session import SessionDeck, StudySession
from routes.utils import error_response
from services.session import parse_session_deck


def _owned_session(session_id: int) -> StudySession | None:
    """Return the session, only if it belongs to the caller (otherwise None, never a 403)."""
    return db.session.scalar(
        select(StudySession).where(
            StudySession.deck_id == session_id,
            StudySession.owner_email == g.account_email,
        )
    )


session = Blueprint("deck", __name__)


def _commit_or_500():
    """Commit; on failure roll back and return the error response (None on success)."""
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return error_response("DatabaseError", "Database error.", 500)
    return None


def _json_body() -> dict | None:
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else None


@session.route("/api/v1/sessions", methods=["GET"])
@require_token
def get_all_sessions():
    """
    Return all studied sessions of the user.

    Answers:
        - 200: [study_session0, study_session1, ...]
        - 401: missing / invalid / already revoked / expired token (see require_token)
    """
    sessions = db.session.scalars(
        select(StudySession)
        .where(StudySession.owner_email == g.account_email)
        .order_by(StudySession.timestamp)
    ).all()
    return jsonify([d.to_dict() for d in sessions]), 200


@session.route("/api/v1/session", methods=["POST"])
@require_token
def create_session():
    """
    Create a new session owned by the user.

    JSON body: {
        "timestamp": str(datetime),
        "tolerance_allowed": bool,
        "is_tolerance_forced": bool
    }

    Notes:
        - Currently the backend only save the last MAX_SESSION_BY_USER sessions.
            It will delete the past ones, this will be change in a future version.

    Answers:
        - 201: {"session": {...}}
        - 400 `InvalidRequest`: body is not a JSON object, or a field is invalid
        - 401: see require_token
    """
    body = _json_body()
    if body is None:
        return error_response("InvalidRequest", "Body must be a JSON object.", 400)

    try:
        fields = parse_session_deck(body)
    except InvalidDeckData as e:
        return error_response("InvalidRequest", f"{e.field}: {e.reason}", 400)

    # TODO: Complete that and the MAX_STUDY_SESSIONS_PER_DAY

    count = db.session.scalar(
        select(func.count())
        .select_from(StudySession)
        .where(StudySession.owner_email == g.account_email)
    )
    if count >= MAX_SESSION_BY_USER:
        # Delete the first session after MAX_SESSION_BY_USER
        # is hit. This behavior is temporary and will be change
        # in v1.1, see [the TODO: about that](../consts.py)
        deleted_session = db.session.scalar(
            delete(StudySession)
            .where(StudySession.owner_email == g.account_email)
            .order_by(StudySession.timestamp.desc())
            .limit(1)
        )
        print(
            f"User, MAX_SESSION_BY_USER ({MAX_SESSION_BY_USER}) being hit, deleting session : {deleted_session.to_dict()}"
        )

    new_session = StudySession(owner_email=g.account_email, **fields)
    db.session.add(new_session)
    if (failure := _commit_or_500()) is not None:
        return failure

    return jsonify({"session": new_session.to_dict()}), 201


@session.route("/api/v1/session/<int:session_id>", methods=["DELETE"])
@require_token
def delete_session(session_id: int):
    """
    Delete studied sessions of the user. Session decks and all they session cards are deleted.

    Answers:
        - 200: {"message": "Session deleted successfully"}
        - 401: see require_token
        - 404 `SessionNotFound`: absent, or not owned by the caller
    """
    owned = _owned_session(session_id)
    if owned is None:
        return error_response("SessionNotFound", "Session not found.", 404)

    db.session.delete(owned)
    if (failure := _commit_or_500()) is not None:
        return failure

    return jsonify({"message": "Session deleted successfully"}), 200


####################################
# SessionDeck related routes which require a study session id
####################################


@session.route("/api/v1/session/<int:study_session_id>/decks", methods=["GET"])
@require_token
def get_all_session_decks(study_session_id: int):
    """
    Return all decks from a studied session of the owner.

    Answers:
        - 200: [session_deck0, session_deck1, ...]
        - 401: missing / invalid / already revoked / expired token (see require_token)
    """
    owned = _owned_session(study_session_id)
    if owned is None:
        return error_response("SessionDeckNotFound", "Session deck not found.", 404)

    session_cards = db.session.scalars(
        select(SessionDeck)
        .where(SessionDeck.deck_id == owned.deck_id)
        .order_by(SessionDeck.position, SessionDeck.card_id)
    ).all()
    return jsonify([c.to_dict() for c in session_cards]), 200


@session.route("/api/v1/session/<int:study_session_id>/decks", methods=["POST"])
@require_token
def create_session_deck(study_session_id: int):
    """
    Create a new session deck of a study session of the owner.

    JSON body: {"name": str, "description": str (optional)}

    Notes:
        - By comparaison to Deck, SessionDeck table can have multiple SessionDeck row with the same name.

    Answers:
        - 201: {"session_deck": {...}}
        - 400 `InvalidRequest`: body is not a JSON object, or a field is invalid
        - 401: see require_token
        - 409 `SessionDeckLimitReached`: the deck already has MAX_DECK_BY_USER cards
    """
    body = _json_body()
    if body is None:
        return error_response("InvalidRequest", "Body must be a JSON object.", 400)

    try:
        fields = parse_session_deck(body)
    except InvalidDeckData as e:
        return error_response("InvalidRequest", f"{e.field}: {e.reason}", 400)

    count = db.session.scalar(
        select(func.count())
        .select_from(SessionDeck)
        .where(SessionDeck.owner_email == g.account_email)
    )
    if count >= MAX_DECK_BY_USER:
        return error_response(
            "SessionDeckLimitReached",
            f"Limit of {MAX_DECK_BY_USER} decks reached.",
            409,
        )
    new_session_deck = SessionDeck(owner_email=g.account_email, **fields)
    db.session.add(new_session_deck)
    if (failure := _commit_or_500()) is not None:
        return failure

    return jsonify({"session_deck": new_session_deck.to_dict()}), 201
