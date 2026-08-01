"""Argon2id password hashing and opaque session-token primitives."""

import hashlib
import secrets

from argon2 import PasswordHasher as Argon2PasswordHasher
from argon2 import Type
from argon2.exceptions import InvalidHashError, VerifyMismatchError


class Argon2idPasswordHasher:
    def __init__(self, time_cost: int = 3, memory_cost: int = 65536, parallelism: int = 2) -> None:
        self._hasher = Argon2PasswordHasher(type=Type.ID, time_cost=time_cost, memory_cost=memory_cost, parallelism=parallelism)

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (InvalidHashError, VerifyMismatchError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        return self._hasher.check_needs_rehash(password_hash)


class SecureSessionTokenGenerator:
    def generate(self) -> str:
        return secrets.token_urlsafe(32)

    def hash(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
