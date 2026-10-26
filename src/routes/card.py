from flask import Blueprint, g, jsonify, request

from database import db
from exceptions import InvalidCardData
from models.base import Card, Deck
from routes.token import require_token
from routes.utils import error_response
from services.card import parse_card

card = Blueprint("card", __name__)


def _owned_card(card_id: int) -> Card | None:
    return (
        db.session.query(Card)
        .join(Deck, Card.deck_id == Deck.deck_id)
        .filter(Card.card_id == card_id, Deck.owner_email == g.account_email)
        .first()
    )


@card.route("/api/v1/card/<int:card_id>", methods=["GET"])
@require_token
def get_card(card_id: int):
    """
    Answers:
        - 200: the card
        - 401: see require_token
        - 404 `CardNotFound`: absent, or not owned by the caller
    """
    card = _owned_card(card_id)
    if card is None:
        return error_response("CardNotFound", "Card not found.", 404)
    return jsonify(card.to_dict()), 200


@card.route("/api/v1/card/<int:card_id>", methods=["DELETE"])
@require_token
def delete_card(card_id: int):
    """
    Answers:
        - 200: the card
        - 401: see require_token
        - 404 `CardNotFound`: absent, or not owned by the caller
    """

    if _owned_card(card_id) is None:
        return error_response("CardNotFound", "Card not found.", 404)
    else:
        db.session.delete(card)
        return jsonify({}), 204


@card.route("/api/v1/card/<int:card_id>", methods=["PATCH"])
@require_token
def update_card(card_id: int):
    """
    Answers:
        - 200: the card updated
        - 401: see require_token
        - 404 `CardNotFound`: absent, or not owned by the caller
    """

    if _owned_card(card_id) is None:
        return error_response("CardNotFound", "Card not found.", 404)

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error_response("InvalidRequest", "Body must be a JSON object.", 400)

    try:
        new_card = parse_card(body)
    except InvalidCardData as e:
        return error_response("InvalidRequest", f"{e.field}: {e.reason}", 400)
    else:
        db.session.query(Card).filter(Card.card_id == card_id).update(new_card)
        db.session.commit()
