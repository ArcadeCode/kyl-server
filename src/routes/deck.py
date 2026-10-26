from flask import Blueprint, g, jsonify, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database import db
from exceptions import InvalidCardData
from models.base import Card, Deck
from routes.token import require_token
from routes.utils import error_response
from services.card import parse_card

deck = Blueprint("deck", __name__)


def _owned_deck(deck_id: int) -> Deck | None:
    return (
        db.session.query(Deck)
        .filter(Deck.deck_id == deck_id, Deck.owner_email == g.account_email)
        .first()
    )


@deck.route("/api/v1/decks", methods=["GET"])
@require_token
def get_all_decks():
    """
    Return all decks of the user.

    Answers:
        - 200: {decks:[...]}
        - 400 `InvalidRequest`
        - 401: missing / invalid / already revoked / expired token (see require_token)
    """
    decks = db.session.scalars(
        select(Deck).where(Deck.owner_email == g.account_email)
    ).all()
    return jsonify([deck.to_dict() for deck in decks]), 200


@deck.route("/api/v1/deck/<int:deck_id>", methods=["DELETE"])
@require_token
def delete_deck(deck_id: int):
    """
    Delete a deck owned by the user. The deck and all its cards are deleted.

    Answers:
        - 200: The deck was deleted successfully
        - 400 `InvalidRequest`
        - 401: missing / invalid / already revoked / expired token
        - 404 `DeckNotFound`: deck not found (doesn't belong to the owner)
    """
    deck = _owned_deck(deck_id)
    if deck is None:
        return error_response("DeckNotFound", "Deck not found.", 404)

    db.session.delete(deck)
    try:
        db.session.commit()
    except (IntegrityError, Exception) as e:
        db.session.rollback()
        return error_response("DatabaseError", str(e), 500)

    return jsonify({"message": "Deck deleted successfully"}), 200


@deck.route("/api/v1/deck/<int:deck_id>", methods=["POST"])
@require_token
def create_deck(deck_id: int):
    """
    Create a new deck owned by the user.

    Request body:
        - {"name": "My new deck", "description": "My favorite deck"}

    Answers:
        - 201: the new deck
        - 400 `InvalidRequest`
        - 401: missing / invalid / already revoked / expired token
        - 400 `InvalidRequest`: empty or invalid body
        - 409 `Conflict`: deck with the same name already exists
    """
    deck = _owned_deck(deck_id)
    if deck is None:
        return error_response("DeckNotFound", "Deck not found.", 404)

    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not body:
        return error_response("InvalidRequest", "Body must be a JSON object.", 400)

    try:
        new_deck = Deck(name=body["name"], description=body["description"])
    except (KeyError, TypeError, ValueError) as e:
        return error_response("InvalidRequest", "Invalid request body.", 400)

    # Check for duplicate name
    existing = (
        db.session.query(Deck)
        .filter(Deck.name == new_deck.name, Deck.owner_email == g.account_email)
        .first()
    )
    if existing is not None:
        return error_response("Conflict", "A deck with this name already exists.", 409)

    db.session.add(new_deck)
    try:
        db.session.commit()
    except (IntegrityError, Exception) as e:
        db.session.rollback()
        return error_response("DatabaseError", str(e), 500)

    return jsonify({"deck": new_deck.to_dict()}), 201


@deck.route("/api/v1/deck/<int:deck_id>", methods=["PATCH"])
@require_token
def update_deck(deck_id: int):
    """
    Update a deck owned by the user.

    Request body:
        - {"name": "Updated deck", "description": "Updated description"}

    Answers:
        - 200: the updated deck
        - 400 `InvalidRequest`
        - 401: missing / invalid / already revoked / expired token
        - 400 `InvalidRequest`: empty or invalid body
        - 404 `DeckNotFound`: deck not found (doesn't belong to the owner)
    """
    deck = _owned_deck(deck_id)
    if deck is None:
        return error_response("DeckNotFound", "Deck not found.", 404)

    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not body:
        return error_response("InvalidRequest", "Body must be a JSON object.", 400)

    try:
        deck.name = body["name"]
        deck.description = body["description"]
    except (KeyError, TypeError, ValueError) as e:
        return error_response("InvalidRequest", "Invalid request body.", 400)

    try:
        db.session.commit()
    except (IntegrityError, Exception) as e:
        db.session.rollback()
        return error_response("DatabaseError", str(e), 500)

    return jsonify({"deck": deck.to_dict()}), 200


####################################
# Card related routes which required Deck id
####################################


@deck.route("/api/v1/deck/<int:deck_id>/cards", methods=["POST"])
@require_token
def create_card(deck_id: int):
    """
    Return all decks of the user.

    Answers:
        - 201: Ressource created, return the card
        - 400 `InvalidRequest`
        - 401: missing / invalid / already revoked / expired token (see require_token)
        - 500: Error when trying to commit the card creation
    """
    deck = _owned_deck(deck_id)
    if deck is None:
        return error_response("DeckNotFound", "Deck not found.", 404)

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error_response("InvalidRequest", "Body must be a JSON object.", 400)

    try:
        new_card: Card = parse_card(body)
    except InvalidCardData as e:
        return error_response("InvalidRequest", f"{e.field}: {e.reason}", 400)

    # Add to session
    db.session.add(new_card)
    db.session.add(deck.cards, new_card)  # Explicitly add to deck's relationship
    db.session.flush()

    try:
        db.session.commit()
    except (IntegrityError, Exception) as e:  # noqa: BLE001
        db.session.rollback()
        return error_response("DatabaseError", str(e), 500)

    return jsonify({"card": new_card.to_dict()}), 201


@deck.route("/api/v1/deck/<int:deck_id>/cards", methods=["GET"])
@require_token
def get_all_cards(deck_id: int):
    """
    Return all cards of the deck owner by the user.

    Answers:
        - 200: [card0, card1, ] All cards from a deck
        - 400 `InvalidRequest`
        - 401: missing / invalid / already revoked / expired token (see require_token)
    """
    deck = _owned_deck(deck_id)
    if deck is None:
        return error_response("DeckNotFound", "Deck not found.", 404)

    cards = db.session.scalars(select(Card).where(Card.deck_id == deck_id)).all()
    return jsonify([card.to_dict() for card in cards]), 200
