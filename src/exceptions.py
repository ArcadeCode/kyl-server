class InvalidCardData(ValueError):
    """Raised when card fields fail validation."""

    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason
        super().__init__(f"{field}: {reason}")


class InvalidDeckData(ValueError):
    """Raised when deck fields fail validation."""

    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason
        super().__init__(f"{field}: {reason}")


class InvalidSessionCardData(ValueError):
    """Raised when session card fields fail validation."""

    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason
        super().__init__(f"{field}: {reason}")


class InvalidSessionDeckData(ValueError):
    """Raised when session deck fields fail validation."""

    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason
        super().__init__(f"{field}: {reason}")


class InvalidStudySessionData(ValueError):
    """Raised when study session fields fail validation."""

    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason
        super().__init__(f"{field}: {reason}")
