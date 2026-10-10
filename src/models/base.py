from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    # I have absolutely no clue why do I need to inherit from DeclarativeBase,
    # but apparently I do so here we are.
    pass


class Account(Base):
    """
    Each account is stored into 'account'. An user can have multiple devices connected to his account.
    """

    __tablename__ = "account"

    email: Mapped[str] = mapped_column(
        String, primary_key=True
    )  # One email only can have one user, so this is our primary key.
    name: Mapped[str] = mapped_column(String, nullable=False)

    password: Mapped[str] = mapped_column(
        String(256), nullable=False
    )  # Hashed password + bcrypt version + bcrypt cost + salt
    salt: Mapped[int] = mapped_column(Integer, nullable=False)


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
    is_tolerant: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)  # Position in a Deck

    deck_id: Mapped[int] = mapped_column(Integer, ForeignKey("deck.id"))

    # Relation vers le Deck
    deck: Mapped["Deck"] = relationship("deck", back_populates="card")  # noqa: UP037


class Deck(Base):
    """
    Represent each Decks stored, each one has an owner.
    Only the owner can view his decks.
    To share a deck, an user need to download his deck and share it
    externally to KYL.
    """

    __tablename__ = "deck"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False, default="Unnamed deck")
    description: Mapped[str] = mapped_column(
        String, nullable=False, default=""
    )  # We don't want null in our DB but desc can be set to "" which
    # essentially do the thing with more security.

    # Relations
    owner_email: Mapped[str] = mapped_column(
        String, ForeignKey("account.email", ondelete="CASCADE"), nullable=False
    )
    owner: Mapped[Account] = relationship("account", back_populates="deck")
    card: Mapped[list[Card]] = relationship(
        "card", back_populates="deck", cascade="all, delete-orphan"
    )
