"""Explicit domain failures for compatibility Account endpoints."""


class AccountOperationError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class OperationUnavailable(AccountOperationError):
    """An intentionally retired operation, not a missing resource."""
