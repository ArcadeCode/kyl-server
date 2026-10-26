from flask import Blueprint, g, jsonify, request
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from auth import require_token
from database import db
from exceptions import InvalidCardData
from models.base import Card, Deck
from routes.utils import error_response
from services.card import parse_card_update

card = Blueprint("card", __name__)


def _owned_card(card_id: int) -> Card | None:
    """The card, only if its deck belongs to the caller (otherwise None, never a 403)."""
    return db.session.scalar(
        select(Card)
        .join(Deck, Card.deck_id == Deck.id)
        .where(Card.card_id == card_id, Deck.owner_email == g.account_email)
    )


def _card_not_found():
    return error_response("CardNotFound", "Card not found.", 404)


@card.route("/api/v1/card/<int:card_id>", methods=["GET"])
@require_token
def get_card(card_id: int):
    """
    Answers:
        - 200: the card
        - 401: see require_token
        - 404 `CardNotFound`: absent, or not owned by the caller
    """
    found = _owned_card(card_id)
    if found is None:
        return _card_not_found()
    return jsonify(found.to_dict()), 200


@card.route("/api/v1/card/<int:card_id>", methods=["DELETE"])
@require_token
def delete_card(card_id: int):
    """
    Answers:
        - 204: the card was deleted (empty body)
        - 401: see require_token
        - 404 `CardNotFound`: absent, or not owned by the caller
    """
    found = _owned_card(card_id)
    if found is None:
        return _card_not_found()

    db.session.delete(found)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return error_response("DatabaseError", "Database error.", 500)

    return "", 204


@card.route("/api/v1/card/<int:card_id>", methods=["PATCH"])
@require_token
def update_card(card_id: int):
    """
    Update a card (partial update). The deck of a card cannot be changed.

    JSON body: any subset of {"question", "answer", "is_tolerant", "position"}, at least one.

    Answers:
        - 200: the updated card
        - 400 `InvalidRequest`: body is not a JSON object, empty, or a field is invalid
        - 401: see require_token
        - 404 `CardNotFound`: absent, or not owned by the caller
    """
    found = _owned_card(card_id)
    if found is None:
        return _card_not_found()

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error_response("InvalidRequest", "Body must be a JSON object.", 400)

    try:
        changes = parse_card_update(body)
    except InvalidCardData as e:
        return error_response("InvalidRequest", f"{e.field}: {e.reason}", 400)

    for field, value in changes.items():
        setattr(found, field, value)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return error_response("DatabaseError", "Database error.", 500)

    return jsonify(found.to_dict()), 200
