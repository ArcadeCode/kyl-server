from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Token(Base):
    """
    Store each communication tokens with a user.
    """

    __tablename__ = "token"

    # BLAKE3 256 bits hash digest of the token. The raw token is never stored.
    token_hash: Mapped[str] = mapped_column(
        String(64), primary_key=True, nullable=False
    )

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
        ForeignKey("account.email"),
        nullable=False,
    )
