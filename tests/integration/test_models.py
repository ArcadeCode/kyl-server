"""Quality of the DB construction: schema, constraints, defaults, cascades, relations."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, inspect, select
from sqlalchemy.exc import IntegrityError

from database import db
from models import (
    Account,
    Card,
    Deck,
    SessionCard,
    SessionDeck,
    StudySession,
    Token,
)

NOW = lambda: datetime.now(timezone.utc)  # noqa: E731


@pytest.fixture
def inspector(app):
    with app.app_context():
        yield inspect(db.engine)


@pytest.fixture
def ctx(app):
    """App context + session for tests that talk to the ORM directly."""
    with app.app_context():
        yield db.session
        db.session.rollback()


def account(email="a@b.fr"):
    return Account(email=email, name="A", password="hash")


# --------------------------------------------------------------------------- schema


EXPECTED_COLUMNS = {
    # table: {column: nullable}
    "account": {"email": False, "name": False, "password": False},
    "deck": {"deck_id": False, "name": False, "description": False, "owner_email": False},
    "card": {
        "card_id": False, "question": False, "answer": False,
        "is_tolerant": False, "position": False, "deck_id": False,
    },
    "token": {
        "token_hash": False, "created_at": False, "expires_at": False,
        "revoked_at": True, "account_email": False,
    },
    "study_session": {
        "id": False, "timestamp": False, "owner_email": False, "tolerance_allowed": False,
    },
    "session_deck": {"id": False, "name": False, "description": False, "study_session_id": False},
    "session_card": {
        "id": False, "question": False, "answer": False,
        "is_tolerant": False, "position": False, "session_deck_id": False,
    },
}

EXPECTED_PRIMARY_KEYS = {
    "account": ["email"], "deck": ["deck_id"], "card": ["card_id"], "token": ["token_hash"],
    "study_session": ["id"], "session_deck": ["id"], "session_card": ["id"],
}

# (table, column) -> (referred table, referred column)
EXPECTED_FOREIGN_KEYS = {
    ("deck", "owner_email"): ("account", "email"),
    ("card", "deck_id"): ("deck", "deck_id"),
    ("token", "account_email"): ("account", "email"),
    ("study_session", "owner_email"): ("account", "email"),
    ("session_deck", "study_session_id"): ("study_session", "id"),
    ("session_card", "session_deck_id"): ("session_deck", "id"),
}


def test_exactly_the_expected_tables_exist(inspector):
    assert set(inspector.get_table_names()) == set(EXPECTED_COLUMNS)


def test_table_names_follow_the_naming_convention(inspector):
    for name in inspector.get_table_names():
        assert name == name.lower() and " " not in name


@pytest.mark.parametrize("table", EXPECTED_COLUMNS)
def test_columns_and_nullability(inspector, table):
    actual = {c["name"]: c["nullable"] for c in inspector.get_columns(table)}
    assert actual == EXPECTED_COLUMNS[table]


@pytest.mark.parametrize("table", EXPECTED_PRIMARY_KEYS)
def test_primary_keys(inspector, table):
    assert inspector.get_pk_constraint(table)["constrained_columns"] == EXPECTED_PRIMARY_KEYS[table]


@pytest.mark.parametrize("table, column", EXPECTED_FOREIGN_KEYS)
def test_foreign_keys_exist_and_cascade_on_delete(inspector, table, column):
    referred_table, referred_column = EXPECTED_FOREIGN_KEYS[table, column]
    matching = [fk for fk in inspector.get_foreign_keys(table) if fk["constrained_columns"] == [column]]
    assert len(matching) == 1
    fk = matching[0]
    assert fk["referred_table"] == referred_table
    assert fk["referred_columns"] == [referred_column]
    assert fk["options"].get("ondelete") == "CASCADE"


@pytest.mark.parametrize("table, column", EXPECTED_FOREIGN_KEYS)
def test_foreign_key_columns_are_indexed(inspector, table, column):
    indexed = [idx["column_names"] for idx in inspector.get_indexes(table)]
    assert [column] in indexed


def test_token_hash_column_fits_a_blake3_hex_digest(inspector):
    column = next(c for c in inspector.get_columns("token") if c["name"] == "token_hash")
    assert column["type"].length == 64


@pytest.mark.parametrize("table, column", [
    ("token", "created_at"), ("token", "expires_at"), ("token", "revoked_at"),
    ("study_session", "timestamp"),
])
def test_datetime_columns_are_timezone_aware(inspector, table, column):
    col = next(c for c in inspector.get_columns(table) if c["name"] == column)
    assert col["type"].timezone is True


# --------------------------------------------------------------------------- constraints


def test_account_email_is_unique(ctx):
    ctx.add(account())
    ctx.commit()
    ctx.add(account())
    with pytest.raises(IntegrityError):
        ctx.commit()


@pytest.mark.parametrize("missing", ["name", "password"])
def test_account_requires_name_and_password(ctx, missing):
    values = {"email": "a@b.fr", "name": "A", "password": "hash"}
    values[missing] = None
    ctx.add(Account(**values))
    with pytest.raises(IntegrityError):
        ctx.commit()


def test_deck_requires_an_existing_owner(ctx):
    ctx.add(Deck(owner_email="ghost@b.fr"))
    with pytest.raises(IntegrityError):
        ctx.commit()


def test_card_requires_an_existing_deck(ctx):
    ctx.add(Card(question="q", answer="a", position=0, deck_id=999))
    with pytest.raises(IntegrityError):
        ctx.commit()


def test_card_requires_question_answer_and_position(ctx):
    ctx.add(account())
    deck = Deck(owner_email="a@b.fr")
    ctx.add(deck)
    ctx.commit()
    for values in ({"answer": "a", "position": 0}, {"question": "q", "position": 0},
                   {"question": "q", "answer": "a"}):
        ctx.add(Card(deck_id=deck.deck_id, **values))
        with pytest.raises(IntegrityError):
            ctx.commit()
        ctx.rollback()


def test_token_requires_an_existing_account(ctx):
    ctx.add(Token(token_hash="h" * 64, created_at=NOW(), expires_at=NOW(), account_email="ghost@b.fr"))
    with pytest.raises(IntegrityError):
        ctx.commit()


def test_token_hash_is_unique(ctx):
    ctx.add(account())
    ctx.commit()
    for _ in range(2):
        ctx.add(Token(token_hash="h" * 64, created_at=NOW(), expires_at=NOW(), account_email="a@b.fr"))
        if _ == 0:
            ctx.commit()
    with pytest.raises(IntegrityError):
        ctx.commit()


def test_token_hash_longer_than_64_chars_is_refused(ctx):
    from sqlalchemy.exc import DataError

    ctx.add(account())
    ctx.commit()
    ctx.add(Token(token_hash="h" * 65, created_at=NOW(), expires_at=NOW(), account_email="a@b.fr"))
    with pytest.raises((DataError, IntegrityError)):
        ctx.commit()


# --------------------------------------------------------------------------- defaults


def test_deck_defaults(ctx):
    ctx.add(account())
    deck = Deck(owner_email="a@b.fr")
    ctx.add(deck)
    ctx.commit()
    assert deck.name == "Unnamed deck"
    assert deck.description == ""
    assert isinstance(deck.deck_id, int)


def test_card_is_tolerant_by_default(ctx):
    ctx.add(account())
    deck = Deck(owner_email="a@b.fr")
    deck.cards.append(Card(question="q", answer="a", position=0))
    ctx.add(deck)
    ctx.commit()
    assert deck.cards[0].is_tolerant is True


def test_token_is_not_revoked_by_default(ctx):
    ctx.add(account())
    token = Token(token_hash="h" * 64, created_at=NOW(), expires_at=NOW(), account_email="a@b.fr")
    ctx.add(token)
    ctx.commit()
    ctx.refresh(token)
    assert token.revoked_at is None


def test_token_datetimes_roundtrip_timezone_aware(ctx):
    ctx.add(account())
    expires = NOW() + timedelta(days=30)
    ctx.add(Token(token_hash="h" * 64, created_at=NOW(), expires_at=expires, account_email="a@b.fr"))
    ctx.commit()
    ctx.expire_all()
    stored = ctx.get(Token, "h" * 64).expires_at
    assert stored.tzinfo is not None
    assert abs(stored - expires) < timedelta(seconds=1)


def test_study_session_timestamp_defaults_to_now_utc(ctx):
    ctx.add(account())
    session = StudySession(owner_email="a@b.fr", tolerance_allowed=True)
    ctx.add(session)
    ctx.commit()
    ctx.refresh(session)
    assert session.timestamp.tzinfo is not None
    assert abs(NOW() - session.timestamp) < timedelta(minutes=1)


def test_session_card_is_tolerant_by_default(ctx):
    ctx.add(account())
    study = StudySession(owner_email="a@b.fr", tolerance_allowed=False)
    snapshot = SessionDeck(name="d", study_session=study)
    snapshot.cards.append(SessionCard(question="q", answer="a", position=0))
    ctx.add(study)
    ctx.commit()
    assert snapshot.cards[0].is_tolerant is True


# --------------------------------------------------------------------------- relationships


def test_relationships_are_wired_both_ways(ctx):
    acc = account()
    deck = Deck(name="d", owner=acc)
    card = Card(question="q", answer="a", position=0, deck=deck)
    token = Token(token_hash="h" * 64, created_at=NOW(), expires_at=NOW(), account=acc)
    ctx.add_all([acc, deck, card, token])
    ctx.commit()
    ctx.expire_all()

    assert [d.name for d in acc.decks] == ["d"]
    assert deck.owner is acc
    assert deck.cards == [card] and card.deck is deck
    assert acc.tokens == [token] and token.account is acc


def test_deck_cards_are_ordered_by_position(ctx):
    acc = account()
    deck = Deck(name="d", owner=acc)
    for position in (2, 0, 1):
        deck.cards.append(Card(question=f"q{position}", answer="a", position=position))
    ctx.add_all([acc, deck])
    ctx.commit()
    ctx.expire_all()
    assert [c.position for c in deck.cards] == [0, 1, 2]


def test_session_snapshot_relations_and_ordering(ctx):
    acc = account()
    study = StudySession(owner=acc, tolerance_allowed=True)
    snapshot = SessionDeck(name="d", study_session=study)
    snapshot.cards += [SessionCard(question="q", answer="a", position=p) for p in (1, 0)]
    ctx.add_all([acc, study])
    ctx.commit()
    ctx.expire_all()
    assert study.owner is acc
    assert study.decks == [snapshot]
    assert [c.position for c in snapshot.cards] == [0, 1]


def test_removing_a_card_from_a_deck_deletes_it(ctx):  # delete-orphan
    acc = account()
    deck = Deck(name="d", owner=acc)
    card = Card(question="q", answer="a", position=0, deck=deck)
    ctx.add_all([acc, deck])
    ctx.commit()
    deck.cards.remove(card)
    ctx.commit()
    assert ctx.scalar(select(Card)) is None


# --------------------------------------------------------------------------- cascades


def populate_everything(ctx):
    """One account owning everything that can hang below an account."""
    acc = account()
    deck = Deck(name="d", owner=acc)
    deck.cards.append(Card(question="q", answer="a", position=0))
    study = StudySession(owner=acc, tolerance_allowed=True)
    snapshot = SessionDeck(name="d", study_session=study)
    snapshot.cards.append(SessionCard(question="q", answer="a", position=0))
    token = Token(token_hash="h" * 64, created_at=NOW(), expires_at=NOW(), account=acc)
    ctx.add_all([acc, deck, study, token])
    ctx.commit()


def count_rows(ctx):
    return {m.__name__: len(ctx.scalars(select(m)).all())
            for m in (Account, Deck, Card, Token, StudySession, SessionDeck, SessionCard)}


def test_deleting_an_account_with_the_orm_deletes_everything_below(ctx):
    populate_everything(ctx)
    assert all(n == 1 for n in count_rows(ctx).values())
    ctx.delete(ctx.get(Account, "a@b.fr"))
    ctx.commit()
    assert all(n == 0 for n in count_rows(ctx).values())


def test_deleting_an_account_in_raw_sql_is_cascaded_by_the_database_itself(ctx):
    """Guards the ON DELETE CASCADE of every foreign key, independently of the ORM."""
    populate_everything(ctx)
    ctx.execute(delete(Account))
    ctx.commit()
    assert all(n == 0 for n in count_rows(ctx).values())


def test_deleting_a_deck_deletes_only_its_cards(ctx):
    populate_everything(ctx)
    ctx.execute(delete(Deck))
    ctx.commit()
    counts = count_rows(ctx)
    assert counts["Deck"] == counts["Card"] == 0
    assert counts["Account"] == counts["Token"] == counts["StudySession"] == 1


def test_deleting_a_study_session_deletes_its_snapshots(ctx):
    populate_everything(ctx)
    ctx.execute(delete(StudySession))
    ctx.commit()
    counts = count_rows(ctx)
    assert counts["StudySession"] == counts["SessionDeck"] == counts["SessionCard"] == 0
    assert counts["Deck"] == counts["Card"] == 1  # live decks are not snapshots


def test_deleting_one_account_does_not_touch_another(ctx):
    populate_everything(ctx)
    ctx.add(Account(email="other@b.fr", name="O", password="h"))
    ctx.add(Token(token_hash="o" * 64, created_at=NOW(), expires_at=NOW(), account_email="other@b.fr"))
    ctx.commit()
    ctx.execute(delete(Account).where(Account.email == "a@b.fr"))
    ctx.commit()
    assert [a.email for a in ctx.scalars(select(Account))] == ["other@b.fr"]
    assert [t.token_hash for t in ctx.scalars(select(Token))] == ["o" * 64]
