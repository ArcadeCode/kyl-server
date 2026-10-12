from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Account, Base


class Token(Base):
    """
    Store each communication token of a user (one per connected device).
    """

    __tablename__ = "token"

    # BLAKE3 256 bits hash digest of the token, hex encoded (64 chars).
    # The raw token is never stored.
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # A token is valid only if NOT revoked AND not expired.
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    account_email: Mapped[str] = mapped_column(
        String,
        ForeignKey("account.email", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account: Mapped[Account] = relationship(back_populates="tokens")
