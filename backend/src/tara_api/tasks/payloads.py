"""AES-GCM protection for transient scheduled-capability inputs."""

from __future__ import annotations

import base64
import binascii
import json
import os
from dataclasses import dataclass
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PAYLOAD_VERSION = 1
MAX_PAYLOAD_BYTES = 4096


@dataclass(frozen=True, slots=True)
class ProtectedTaskPayload:
    nonce: bytes
    ciphertext: bytes
    payload_version: int
    key_version: str


class TaskPayloadProtector:
    """Encrypt only validated target/parameter inputs using task-bound AAD."""

    def __init__(self, encoded_key: str, *, key_version: str = "v1") -> None:
        try:
            key = base64.b64decode(encoded_key, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ValueError("task_payload_key_invalid") from error
        if len(key) != 32 or not key_version or len(key_version) > 32:
            raise ValueError("task_payload_key_invalid")
        self._cipher = AESGCM(key)
        self._key_version = key_version

    def protect(self, *, task_id: UUID, owner_id: UUID, capability_id: str, binding_hash: str, target: str, parameters: dict[str, str | int | bool | None]) -> ProtectedTaskPayload:
        plaintext = self._encode(target, parameters)
        nonce = os.urandom(12)
        return ProtectedTaskPayload(nonce, self._cipher.encrypt(nonce, plaintext, self._aad(task_id, owner_id, capability_id, binding_hash)), PAYLOAD_VERSION, self._key_version)

    def reveal(self, *, task_id: UUID, owner_id: UUID, capability_id: str, binding_hash: str, payload_version: int, nonce: bytes, ciphertext: bytes) -> tuple[str, dict[str, str | int | bool | None]]:
        if payload_version != PAYLOAD_VERSION or len(nonce) != 12 or not ciphertext:
            raise ValueError("task_payload_invalid")
        try:
            decoded = json.loads(self._cipher.decrypt(nonce, ciphertext, self._aad(task_id, owner_id, capability_id, binding_hash)))
        except (InvalidTag, ValueError, json.JSONDecodeError):
            raise ValueError("task_payload_invalid") from None
        if not isinstance(decoded, dict) or set(decoded) != {"parameters", "target", "version"} or decoded["version"] != PAYLOAD_VERSION:
            raise ValueError("task_payload_invalid")
        target, parameters = decoded["target"], decoded["parameters"]
        if not isinstance(target, str) or not isinstance(parameters, dict) or any(not isinstance(key, str) or not isinstance(value, (str, int, bool, type(None))) for key, value in parameters.items()):
            raise ValueError("task_payload_invalid")
        return target, parameters

    @staticmethod
    def _aad(task_id: UUID, owner_id: UUID, capability_id: str, binding_hash: str) -> bytes:
        return f"{PAYLOAD_VERSION}|{task_id}|{owner_id}|{capability_id}|{binding_hash}".encode()

    @staticmethod
    def _encode(target: str, parameters: dict[str, str | int | bool | None]) -> bytes:
        try:
            encoded = json.dumps({"parameters": parameters, "target": target, "version": PAYLOAD_VERSION}, allow_nan=False, separators=(",", ":"), sort_keys=True).encode()
        except (TypeError, ValueError) as error:
            raise ValueError("task_payload_invalid") from error
        if len(encoded) > MAX_PAYLOAD_BYTES:
            raise ValueError("task_payload_invalid")
        return encoded


class UnavailableTaskPayloadProtector:
    """Fail closed until a dedicated scheduler encryption key is configured."""

    def protect(self, **_kwargs: object) -> ProtectedTaskPayload:
        raise ValueError("task_payload_unavailable")
