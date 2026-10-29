from flask import g, jsonify
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from auth import require_token
from database import db
from models.session import SessionCard, SessionDeck, StudySession
from routes.session import session
from routes.utils import error_response


def _owned_session_card(session_card_id: int) -> SessionCard | None:
    """
    Return the session card, only if its deck belongs to the caller (otherwise None, never a 403).

    As a reminder for each Session :
        each SessionCard are linked to one SessionDeck
        all SessionDeck are linked to one StudySession
    """
    return db.session.scalar(
        select(SessionCard)
        .join(SessionDeck, SessionCard.deck_id == SessionDeck.deck_id)
        .join(StudySession, SessionDeck.decks == StudySession.decks)
        .where(
            SessionCard.session_card_id == session_card_id,
            SessionDeck.owner_email == g.account_email,
        )
    )


def _session_card_not_found():
    return error_response("SessionCardNotFound", "Session card not found.", 404)


@session.route("/api/v1/session/card/<int:session_card_id>", methods=["GET"])
@require_token
def get_session_card(session_card_id: int):
    """
    Answers:
        - 200: the session card
        - 401: see require_token
        - 404 `SessionCardNotFound`: absent, or not owned by the caller
    """
    found = _owned_session_card(session_card_id)
    if found is None:
        return _session_card_not_found()
    return jsonify(found.to_dict()), 200


@session.route("/api/v1/session/card/<int:session_card_id>", methods=["DELETE"])
@require_token
def delete_card(session_card_id: int):
    """
    Answers:
        - 204: the session card was deleted (empty body)
        - 401: see require_token
        - 404 `SessionCardNotFound`: absent, or not owned by the caller
    """
    found = _owned_session_card(session_card_id)
    if found is None:
        return _session_card_not_found()

    db.session.delete(found)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return error_response("DatabaseError", "Database error.", 500)

    return "", 204
