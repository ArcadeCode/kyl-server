from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Relationship


class User(DeclarativeBase):
    """
    Each users are stored into 'user'. An user can have multiple devices connected.
    """

    __tablename__ = "user"

    email = Column(
        String, primary_key=True
    )  # One email only can have one user, so this is our primary key.
    name = (Column(String, nullable=False),)
    password = Column(Integer, nullable=False)  # Password need to be hashed


class Card(DeclarativeBase):
    __tablename__ = "card"

    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    question = Column(String, nullable=False)
    answer = Column(String, nullable=False)
    isTolerant = Column(Boolean, default=False)
    position = Column(Integer, nullable=False)  # Position in a Deck

    deck_id = Column(Integer, ForeignKey("deck.id"))

    # Relation vers le Deck
    deck = Relationship("deck", back_populates="card")


class Deck(DeclarativeBase):
    """
    Represent each Decks stored, each one has an owner.
    Only the owner can view his decks.
    To share a deck, an user need to download his deck and share it
    externaly to KYL.
    """

    __tablename__ = "deck"

    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    name = Column(String, nullable=False, default="Unnamed deck")
    description = Column(
        String, nullable=False, default=""
    )  # We don't want null in our DB but desc can be set to "" wich
    # esentially do the thing with more security.

    # Relations
    owner = Relationship("user", back_populates="deck")
    cards = Relationship("card", back_populates="deck", cascade="all, delete-orphan")
