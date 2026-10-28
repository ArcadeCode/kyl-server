from flask import Blueprint, g, jsonify, request
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from auth import require_token
from consts import MAX_CARD_BY_DECK, MAX_DECK_BY_USER
from database import db
from exceptions import InvalidCardData, InvalidDeckData
from models.base import Card, Deck
from routes.utils import error_response
from services.card import parse_card
from services.deck import parse_deck, parse_deck_update

deck = Blueprint("deck", __name__)


def _owned_deck(deck_id: int) -> Deck | None:
    """The deck, only if it belongs to the caller (otherwise None, never a 403)."""
    return db.session.scalar(
        select(Deck).where(Deck.deck_id == deck_id, Deck.owner_email == g.account_email)
    )


def _name_taken(name: str, ignore_deck_id: int | None = None) -> bool:
    query = select(Deck.deck_id).where(
        Deck.name == name, Deck.owner_email == g.account_email
    )
    if ignore_deck_id is not None:
        query = query.where(Deck.deck_id != ignore_deck_id)
    return db.session.scalar(query.limit(1)) is not None


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


@deck.route("/api/v1/decks", methods=["GET"])
@require_token
def get_all_decks():
    """
    Return all decks of the user.

    Answers:
        - 200: [deck0, deck1, ...]
        - 401: missing / invalid / already revoked / expired token (see require_token)
    """
    decks = db.session.scalars(
        select(Deck).where(Deck.owner_email == g.account_email).order_by(Deck.deck_id)
    ).all()
    return jsonify([d.to_dict() for d in decks]), 200


@deck.route("/api/v1/decks", methods=["POST"])
@require_token
def create_deck():
    """
    Create a new deck owned by the user.

    JSON body: {"name": str, "description": str (optional)}

    Answers:
        - 201: {"deck": {...}}
        - 400 `InvalidRequest`: body is not a JSON object, or a field is invalid
        - 401: see require_token
        - 409 `DeckLimitReached`: the user already has MAX_DECK_BY_USER decks
        - 409 `Conflict`: the user already has a deck with this name
    """
    body = _json_body()
    if body is None:
        return error_response("InvalidRequest", "Body must be a JSON object.", 400)

    try:
        fields = parse_deck(body)
    except InvalidDeckData as e:
        return error_response("InvalidRequest", f"{e.field}: {e.reason}", 400)

    count = db.session.scalar(
        select(func.count())
        .select_from(Deck)
        .where(Deck.owner_email == g.account_email)
    )
    if count >= MAX_DECK_BY_USER:
        return error_response(
            "DeckLimitReached", f"Limit of {MAX_DECK_BY_USER} decks reached.", 409
        )
    if _name_taken(fields["name"]):
        return error_response("Conflict", "A deck with this name already exists.", 409)

    new_deck = Deck(owner_email=g.account_email, **fields)
    db.session.add(new_deck)
    if (failure := _commit_or_500()) is not None:
        return failure

    return jsonify({"deck": new_deck.to_dict()}), 201


@deck.route("/api/v1/deck/<int:deck_id>", methods=["PATCH"])
@require_token
def update_deck(deck_id: int):
    """
    Update a deck owned by the user (partial update).

    JSON body: any subset of {"name": str, "description": str}, at least one.

    Answers:
        - 200: {"deck": {...}}
        - 400 `InvalidRequest`: body is not a JSON object, empty, or a field is invalid
        - 401: see require_token
        - 404 `DeckNotFound`: absent, or not owned by the caller
        - 409 `Conflict`: another deck of the user already has this name
    """
    owned = _owned_deck(deck_id)
    if owned is None:
        return error_response("DeckNotFound", "Deck not found.", 404)

    body = _json_body()
    if body is None:
        return error_response("InvalidRequest", "Body must be a JSON object.", 400)

    try:
        changes = parse_deck_update(body)
    except InvalidDeckData as e:
        return error_response("InvalidRequest", f"{e.field}: {e.reason}", 400)

    if "name" in changes and _name_taken(changes["name"], ignore_deck_id=owned.deck_id):
        return error_response("Conflict", "A deck with this name already exists.", 409)

    for field, value in changes.items():
        setattr(owned, field, value)
    if (failure := _commit_or_500()) is not None:
        return failure

    return jsonify({"deck": owned.to_dict()}), 200


@deck.route("/api/v1/deck/<int:deck_id>", methods=["DELETE"])
@require_token
def delete_deck(deck_id: int):
    """
    Delete a deck owned by the user. The deck and all its cards are deleted.

    Answers:
        - 200: {"message": "Deck deleted successfully"}
        - 401: see require_token
        - 404 `DeckNotFound`: absent, or not owned by the caller
    """
    owned = _owned_deck(deck_id)
    if owned is None:
        return error_response("DeckNotFound", "Deck not found.", 404)

    db.session.delete(owned)
    if (failure := _commit_or_500()) is not None:
        return failure

    return jsonify({"message": "Deck deleted successfully"}), 200


####################################
# Card related routes which require a deck id
####################################


@deck.route("/api/v1/deck/<int:deck_id>/cards", methods=["POST"])
@require_token
def create_card(deck_id: int):
    """
    Add a card to a deck owned by the user.

    JSON body: {"question": str, "answer": str, "is_tolerant": bool, "position": int >= 0}

    Answers:
        - 201: {"card": {...}}
        - 400 `InvalidRequest`: body is not a JSON object, or a field is missing / invalid
          (wrong type, text longer than the limits of consts.py, negative position)
        - 401: see require_token
        - 404 `DeckNotFound`: absent, or not owned by the caller
        - 409 `CardLimitReached`: the deck already has MAX_CARD_BY_DECK cards
    """
    owned = _owned_deck(deck_id)
    if owned is None:
        return error_response("DeckNotFound", "Deck not found.", 404)

    body = _json_body()
    if body is None:
        return error_response("InvalidRequest", "Body must be a JSON object.", 400)

    try:
        new_card: Card = parse_card(body)
    except InvalidCardData as e:
        return error_response("InvalidRequest", f"{e.field}: {e.reason}", 400)

    count = db.session.scalar(
        select(func.count()).select_from(Card).where(Card.deck_id == owned.deck_id)
    )
    if count >= MAX_CARD_BY_DECK:
        return error_response(
            "CardLimitReached",
            f"Limit of {MAX_CARD_BY_DECK} cards per deck reached.",
            409,
        )

    new_card.deck_id = owned.deck_id
    db.session.add(new_card)
    if (failure := _commit_or_500()) is not None:
        return failure

    return jsonify({"card": new_card.to_dict()}), 201


@deck.route("/api/v1/deck/<int:deck_id>/cards", methods=["GET"])
@require_token
def get_all_cards(deck_id: int):
    """
    Return all cards of a deck owned by the user, sorted by position.

    Answers:
        - 200: [card0, card1, ...]
        - 401: see require_token
        - 404 `DeckNotFound`: absent, or not owned by the caller
    """
    owned = _owned_deck(deck_id)
    if owned is None:
        return error_response("DeckNotFound", "Deck not found.", 404)

    cards = db.session.scalars(
        select(Card)
        .where(Card.deck_id == owned.deck_id)
        .order_by(Card.position, Card.card_id)
    ).all()
    return jsonify([c.to_dict() for c in cards]), 200
