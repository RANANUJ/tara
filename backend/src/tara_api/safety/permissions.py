"""Default-deny permission service with explicit capability scopes."""

from tara_api.domain.models import PermissionScope, ToolRequest


class DefaultDenyPermissionService:
    """Allow only exact explicitly granted capabilities and targets."""

    def __init__(self, granted_scopes: tuple[PermissionScope, ...] = ()) -> None:
        self._granted_scopes = {scope.capability: scope for scope in granted_scopes}

    def grant(self, scope: PermissionScope) -> None:
        self._granted_scopes[scope.capability] = scope

    def revoke(self, capability: str) -> None:
        self._granted_scopes.pop(capability, None)

    def is_allowed(self, scope: PermissionScope, request: ToolRequest) -> bool:
        granted_scope = self._granted_scopes.get(scope.capability)
        if granted_scope is None:
            return False
        target = request.arguments.get("target")
        return isinstance(target, str) and granted_scope.allows(target) or target is None and granted_scope.allows()
