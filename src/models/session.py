from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Account, Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StudySession(Base):
    """
    One study session of a user. It owns the immutable snapshots
    (SessionDeck / SessionCard) of what was studied at that moment.
    """

    __tablename__ = "study_session"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    owner_email: Mapped[str] = mapped_column(
        String,
        ForeignKey("account.email", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tolerance_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)

    owner: Mapped[Account] = relationship()
    decks: Mapped[list["SessionDeck"]] = relationship(
        back_populates="study_session", cascade="all, delete-orphan"
    )


class SessionDeck(Base):
    """
    Immutable historical copy of a Deck at a given moment.
    """

    __tablename__ = "session_deck"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")

    study_session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("study_session.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    study_session: Mapped[StudySession] = relationship(back_populates="decks")
    cards: Mapped[list["SessionCard"]] = relationship(
        back_populates="session_deck",
        cascade="all, delete-orphan",
        order_by="SessionCard.position",
    )


class SessionCard(Base):
    """
    Immutable historical copy of a Card at a given moment.
    """

    __tablename__ = "session_card"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, nullable=False
    )
    question: Mapped[str] = mapped_column(String, nullable=False)
    answer: Mapped[str] = mapped_column(String, nullable=False)
    is_tolerant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Used to retrieve the original order when a session deck was shuffled.
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    session_deck_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("session_deck.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_deck: Mapped[SessionDeck] = relationship(back_populates="cards")
