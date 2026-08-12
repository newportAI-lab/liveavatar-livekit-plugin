class FacemarketError(Exception):
    """Base exception for Facemarket plugin failures."""


class ConfigurationError(FacemarketError):
    """Raised when Facemarket configuration is invalid."""


class SessionAlreadyStartedError(FacemarketError):
    """Raised when a session is started more than once."""


class SessionStoppedError(FacemarketError):
    """Raised when an operation requires an active session."""


class APIError(FacemarketError):
    """Raised when the Facemarket API returns an error."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"Facemarket API error {code}: {message}")


class SessionStartError(APIError):
    """Raised when the Facemarket API cannot start a session."""


class DataChannelProtocolError(FacemarketError):
    """Raised when a Facemarket Data Channel event is invalid."""
