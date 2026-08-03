"""Focused AES-GCM task-payload tests without provider or network access."""

from uuid import UUID, uuid4

import pytest

from tara_api.tasks.payloads import TaskPayloadProtector

KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


def _protected() -> tuple[TaskPayloadProtector, UUID, UUID, str]:
    return TaskPayloadProtector(KEY), uuid4(), uuid4(), "filesystem.list"


def test_payload_encrypts_round_trips_with_fresh_nonce() -> None:
    protector, task_id, owner_id, capability_id = _protected()
    first = protector.protect(task_id=task_id, owner_id=owner_id, capability_id=capability_id, binding_hash="a" * 64, target=".", parameters={"depth": 1})
    second = protector.protect(task_id=task_id, owner_id=owner_id, capability_id=capability_id, binding_hash="a" * 64, target=".", parameters={"depth": 1})
    assert first.nonce != second.nonce and first.ciphertext != second.ciphertext
    assert b'"target":"."' not in first.ciphertext
    assert protector.reveal(task_id=task_id, owner_id=owner_id, capability_id=capability_id, binding_hash="a" * 64, payload_version=first.payload_version, nonce=first.nonce, ciphertext=first.ciphertext) == (".", {"depth": 1})


@pytest.mark.parametrize("field", ["task", "owner", "capability", "binding"])
def test_payload_rejects_substitution(field: str) -> None:
    protector, task_id, owner_id, capability_id = _protected()
    protected = protector.protect(task_id=task_id, owner_id=owner_id, capability_id=capability_id, binding_hash="a" * 64, target=".", parameters={})
    task, owner, capability, binding = task_id, owner_id, capability_id, "a" * 64
    if field == "task":
        task = uuid4()
    if field == "owner":
        owner = uuid4()
    if field == "capability":
        capability = "other.capability"
    if field == "binding":
        binding = "b" * 64
    with pytest.raises(ValueError, match="task_payload_invalid"):
        protector.reveal(task_id=task, owner_id=owner, capability_id=capability, binding_hash=binding, payload_version=protected.payload_version, nonce=protected.nonce, ciphertext=protected.ciphertext)
