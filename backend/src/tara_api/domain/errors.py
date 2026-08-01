"""Stable domain errors for policy and confirmation denials."""


class ToolArgumentValidationError(ValueError):
    """Raised when a tool request does not satisfy its typed argument schema."""


class ConfirmationDeniedError(RuntimeError):
    """Raised when an authorization is missing, invalid, expired, or consumed."""
