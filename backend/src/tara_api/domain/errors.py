"""Framework-independent application errors with safe public contracts."""

from dataclasses import dataclass, field
from enum import StrEnum


class ErrorCode(StrEnum):
    VALIDATION_FAILED = "validation_failed"
    AUTHENTICATION_REQUIRED = "authentication_required"
    AUTHENTICATION_FAILED = "authentication_failed"
    PERMISSION_DENIED = "permission_denied"
    RESOURCE_NOT_FOUND = "resource_not_found"
    CONFLICT = "conflict"
    RATE_LIMITED = "rate_limited"
    RESOURCE_EXPIRED = "resource_expired"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    OPERATION_TIMEOUT = "operation_timeout"
    INVALID_STATE = "invalid_state"
    UNSUPPORTED_OPERATION = "unsupported_operation"
    INTERNAL_ERROR = "internal_error"


@dataclass(slots=True)
class ApplicationError(Exception):
    code: ErrorCode
    public_message: str
    details: dict[str, str] = field(default_factory=dict)
    retryable: bool = False


class ValidationError(ApplicationError):
    def __init__(self, details: dict[str, str] | None = None) -> None:
        super().__init__(ErrorCode.VALIDATION_FAILED, "The request is invalid.", details or {})


class AuthenticationRequiredError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.AUTHENTICATION_REQUIRED, "Authentication is required.")


class AuthenticationFailedError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.AUTHENTICATION_FAILED, "Authentication failed.")


class PermissionDeniedError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.PERMISSION_DENIED, "Permission is denied.")


class ResourceNotFoundError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.RESOURCE_NOT_FOUND, "The requested resource was not found.")


class ConflictError(ApplicationError):
    def __init__(self, message: str = "The request conflicts with the current state.") -> None:
        super().__init__(ErrorCode.CONFLICT, message)


class RateLimitedError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.RATE_LIMITED, "Too many requests. Try again later.", retryable=True)


class ExpiredResourceError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.RESOURCE_EXPIRED, "The requested resource has expired.")


class DependencyUnavailableError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.DEPENDENCY_UNAVAILABLE, "A required service is unavailable.", retryable=True)


class OperationTimeoutError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.OPERATION_TIMEOUT, "The operation timed out.", retryable=True)


class InvalidStateError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.INVALID_STATE, "The operation is not valid in the current state.")


class UnsupportedOperationError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.UNSUPPORTED_OPERATION, "This operation is not supported.")


class InternalError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.INTERNAL_ERROR, "An internal error occurred.")


class ToolArgumentValidationError(ValueError):
    """Typed internal validation signal used by the M3 tool boundary."""
