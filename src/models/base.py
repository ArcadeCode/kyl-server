from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Common declarative base of every ORM class."""


class Account(Base):
    """
    Each account is stored into 'account'. A user can have multiple devices
    connected to his account (one Token per device).
    """

    __tablename__ = "account"

    # One email can only have one user, so this is our primary key.
    email: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # bcrypt hash: it already embeds the algorithm version, the cost and the salt.
    password: Mapped[str] = mapped_column(String(256), nullable=False)

    decks: Mapped[list["Deck"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    tokens: Mapped[list["Token"]] = relationship(  # noqa: F821
        back_populates="account", cascade="all, delete-orphan"
    )


class Deck(Base):
    """
    Represent each Deck stored, each one has an owner.
    Only the owner can view his decks.
    To share a deck, a user needs to download it and share it externally to KYL.
    """

    __tablename__ = "deck"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False, default="Unnamed deck")
    # We don't want NULL in our DB: an empty description is stored as "".
    description: Mapped[str] = mapped_column(String, nullable=False, default="")

    owner_email: Mapped[str] = mapped_column(
        String,
        ForeignKey("account.email", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner: Mapped[Account] = relationship(back_populates="decks")
    cards: Mapped[list["Card"]] = relationship(
        back_populates="deck",
        cascade="all, delete-orphan",
        order_by="Card.position",
    )


class Card(Base):
    """
    Represent each Card stored, each one is associated to a Deck.
    Only the owner of the deck can view his cards.
    """

    __tablename__ = "card"

    card_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, nullable=False
    )
    question: Mapped[str] = mapped_column(String, nullable=False)
    answer: Mapped[str] = mapped_column(String, nullable=False)
    # Same default as the KYL App ('tolerant' unless the card says otherwise).
    is_tolerant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)  # Position in a Deck

    deck_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("deck.id", ondelete="CASCADE"), nullable=False, index=True
    )
    deck: Mapped[Deck] = relationship(back_populates="cards")
