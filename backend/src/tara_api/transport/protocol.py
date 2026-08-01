"""Strict JSON-only M6 protocol envelopes and transport errors."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

PROTOCOL_VERSION = 1


class TransportErrorCode(StrEnum):
    AUTHENTICATION_REQUIRED = "authentication_required"
    INVALID_TICKET = "invalid_ticket"
    EXPIRED_TICKET = "expired_ticket"
    REUSED_TICKET = "reused_ticket"
    UNSUPPORTED_PROTOCOL = "unsupported_protocol"
    INVALID_EVENT = "invalid_event"
    INVALID_SEQUENCE = "invalid_sequence"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    RATE_LIMITED = "rate_limited"
    HELLO_TIMEOUT = "hello_timeout"
    CONNECTION_LIMIT = "connection_limit_exceeded"
    SESSION_INVALIDATED = "session_invalidated"
    INTERNAL_ERROR = "internal_transport_error"


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[1]
    event_id: UUID
    session_id: UUID
    sequence: int = Field(ge=0)
    timestamp: datetime
    type: str = Field(pattern=r"^(session\.(hello|ping|close)|client\.ack|audio\.(session\.(start|stop|cancel)|format|flush))$")
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must include UTC offset")
        return value.astimezone(UTC)


class ServerEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[1] = 1
    event_id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    sequence: int = Field(ge=0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)


def error_event(session_id: UUID, sequence: int, code: TransportErrorCode, message: str) -> ServerEvent:
    return ServerEvent(session_id=session_id, sequence=sequence, type="session.error", payload={"code": code.value, "message": message})
