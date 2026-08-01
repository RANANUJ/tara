from uuid import uuid4

import pytest

from tara_api.agent.context_policy import ContextSensitivityPolicy
from tara_api.config.settings import Settings
from tara_api.domain.agent import ContextItem, ContextSensitivity, ContextSourceKind, ContextSourceMetadata


def item(sensitivity: ContextSensitivity) -> ContextItem:
    return ContextItem("safe", sensitivity, ContextSourceMetadata(ContextSourceKind.STRUCTURED_MEMORY, uuid4()))


def test_context_policy_excludes_private_sensitive_and_restricted_by_default() -> None:
    policy = ContextSensitivityPolicy((ContextSensitivity.NORMAL,))
    normal = item(ContextSensitivity.NORMAL)

    assert policy.filter((normal, item(ContextSensitivity.PRIVATE), item(ContextSensitivity.SENSITIVE))) == (normal,)
    assert policy.allows(ContextSensitivity.NORMAL) is True
    assert policy.allows(ContextSensitivity.PRIVATE) is False
    assert policy.allows(ContextSensitivity.SENSITIVE) is False
    assert policy.allows(ContextSensitivity.RESTRICTED) is False


def test_context_policy_requires_explicit_private_or_sensitive_enablement_and_never_allows_restricted() -> None:
    policy = ContextSensitivityPolicy((ContextSensitivity.NORMAL, ContextSensitivity.PRIVATE, ContextSensitivity.SENSITIVE))

    assert policy.allows(ContextSensitivity.PRIVATE) is True
    assert policy.allows(ContextSensitivity.SENSITIVE) is True
    with pytest.raises(ValueError, match="restricted"):
        ContextSensitivityPolicy((ContextSensitivity.RESTRICTED,))


def test_context_settings_default_to_normal_and_reject_restricted() -> None:
    assert Settings(_env_file=None).agent_context_allowed_sensitivities == ("normal",)
    with pytest.raises(ValueError, match="restricted"):
        Settings(_env_file=None, agent_context_allowed_sensitivities=("normal", "restricted"))
