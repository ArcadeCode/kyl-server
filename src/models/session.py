from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Relationship


class SessionCard(DeclarativeBase):
    """
    Represent an immutable historical copy of a Card t-uplet at a given moment.
    """

    __tablename__ = "sessionCard"

    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    question = Column(String, nullable=False)
    answer = Column(String, nullable=False)
    isTolerant = Column(Boolean, default=False)
    position = Column(
        Integer, nullable=False
    )  # Use to retrieve position when shuffling sessions decks.

    deck_id = Column(Integer, ForeignKey("sessionDeck.id"))

    deck = Relationship("sessionDeck", back_populates="sessionCard")


class SessionDeck(DeclarativeBase):
    """
    Represent an immuatable historical copy of a Card t-uplet at a given moment.
    """

    __tablename__ = "sessionDeck"

    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=False)

    # Relations
    owner = Relationship("user", back_populates="sessionDeck")
    cards = Relationship(
        "sessionCard", back_populates="sessionDeck", cascade="all, delete-orphan"
    )


class Session(DeclarativeBase):
    __tablename__ = "session"

    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    timestamp = Column(
        Integer, nullable=False
    )  # Timestamp represented by unix epoch system.
    owner = ForeignKey("user.email")

    toleranceAllowed = Column(Boolean, nullable=False)
