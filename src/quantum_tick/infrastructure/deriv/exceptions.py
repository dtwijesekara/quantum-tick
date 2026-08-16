class DerivApiError(Exception):
    """Raised when the Deriv API returns an explicit error payload."""

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


class DerivAuthError(DerivApiError):
    """Raised when the REST account-bootstrap / OTP handshake fails."""
