from flask import g, jsonify, request
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from auth import require_token
from consts import MAX_CARD_BY_DECK
from database import db
from exceptions import InvalidSessionCardData
from models.session import SessionCard, SessionDeck, StudySession
from routes.session import session
from routes.utils import error_response
from services.session import parse_session_card


def _owned_session_deck(session_deck_id: int) -> SessionDeck | None:
    """
    Return the session card, only if its deck belongs to the caller (otherwise None, never a 403).

    As a reminder for each Session :
        each SessionCard are linked to one SessionDeck
        all SessionDeck are linked to one StudySession
    """
    return db.session.scalar(
        select(SessionCard)
        .join(StudySession, SessionDeck.decks == StudySession.decks)
        .where(
            SessionDeck.session_deck_id == session_deck_id,
            SessionDeck.owner_email == g.account_email,
        )
    )


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


@session.route(
    "/api/v1/session/deck/<int:session_deck_id>",
    methods=["DELETE"],
)
@require_token
def delete_deck(session_deck_id: int):
    """
    Delete a session deck of a study session of the owner.

    Answers:
        - 200: {"message": "Session deck deleted successfully"}
        - 401: see require_token
        - 404 `SessionDeckNotFound`: absent, or not owned by the caller
    """
    owned = _owned_session_deck(session_deck_id)
    if owned is None:
        return error_response("SessionDeckNotFound", "Session deck not found.", 404)

    db.session.delete(owned)
    if (failure := _commit_or_500()) is not None:
        return failure

    return jsonify({"message": "Session deck deleted successfully"}), 200


####################################
# SessionCard related routes which require a session deck id
####################################


@session.route(
    "/api/v1/session/deck/<int:session_deck_id>/cards",
    methods=["POST"],
)
@require_token
def create_card(session_deck_id: int):
    """
    Add a session card to a deck of a study session of the owner.

    JSON body: {"question": str, "answer": str, "is_tolerant": bool, "position": int >= 0}

    Answers:
        - 201: {"session_card": {...}}
        - 400 `InvalidRequest`: body is not a JSON object, or a field is missing / invalid
          (wrong type, text longer than the limits of consts.py, negative position)
        - 401: see require_token
        - 404 `SessionDeckNotFound`: absent, or not owned by the caller
        - 409 `SessionCardLimitReached`: the deck already has MAX_CARD_BY_DECK cards
    """
    owned = _owned_session_deck(session_deck_id)
    if owned is None:
        return error_response("SessionDeckNotFound", "Session deck not found.", 404)

    body = _json_body()
    if body is None:
        return error_response("InvalidRequest", "Body must be a JSON object.", 400)

    try:
        new_session_card: SessionCard = parse_session_card(body)
    except InvalidSessionCardData as e:
        return error_response("InvalidRequest", f"{e.field}: {e.reason}", 400)

    count = db.session.scalar(
        select(func.count())
        .select_from(SessionCard)
        .where(SessionCard.deck_id == owned.deck_id)
    )
    if count >= MAX_CARD_BY_DECK:
        return error_response(
            "SessionCardLimitReached",
            f"Limit of {MAX_CARD_BY_DECK} cards per deck reached.",
            409,
        )

    new_session_card.deck_id = owned.deck_id
    db.session.add(new_session_card)
    if (failure := _commit_or_500()) is not None:
        return failure

    return jsonify({"session_card": new_session_card.to_dict()}), 201


@session.route(
    "/api/v1/session/deck/<int:session_deck_id>/cards",
    methods=["POST"],
)
@require_token
def get_all_cards(session_deck_id: int):
    """
    Return all cards of a deck owned by the user, sorted by position.

    Answers:
        - 200: [session_card0, session_card1, ...]
        - 401: see require_token
        - 404 `DeckNotFound`: absent, or not owned by the caller
    """
    owned = _owned_session_deck(session_deck_id)
    if owned is None:
        return error_response("DeckNotFound", "Deck not found.", 404)

    session_cards = db.session.scalars(
        select(SessionCard)
        .where(SessionCard.deck_id == owned.deck_id)
        .order_by(SessionCard.position, SessionCard.card_id)
    ).all()
    return jsonify([c.to_dict() for c in session_cards]), 200
