from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class SessionCard(Base):
    """
    Represent an immutable historical copy of a Card t-uplet at a given moment.
    """

    __tablename__ = "sessionCard"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, nullable=False
    )
    question: Mapped[str] = mapped_column(String, nullable=False)
    answer: Mapped[str] = mapped_column(String, nullable=False)
    isTolerant: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # Use to retrieve position when shuffling sessions decks.

    deck_id: Mapped[int] = mapped_column(Integer, ForeignKey("sessionDeck.id"))

    deck: Mapped["SessionDeck"] = relationship(  # noqa: UP037
        "sessionDeck", back_populates="sessionCard"
    )


class SessionDeck(Base):
    """
    Represent an immutable historical copy of a Card t-uplet at a given moment.
    """

    __tablename__ = "sessionDeck"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)

    # Relations
    owner: Mapped[str] = relationship("account", back_populates="sessionDeck")
    cards: Mapped[list[SessionCard]] = relationship(
        "sessionCard", back_populates="sessionDeck", cascade="all, delete-orphan"
    )


class StudySession(Base):
    __tablename__ = "studySession"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    owner: Mapped[str] = mapped_column(String, ForeignKey("account.email"))

    toleranceAllowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
