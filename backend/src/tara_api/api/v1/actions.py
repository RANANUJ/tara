"""Authenticated M13 capability catalog and constrained read-only proof endpoint."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from tara_api.api.v1.auth import authenticated_context
from tara_api.capabilities.service import CapabilityService
from tara_api.domain.auth import AuthenticatedOwnerContext

router = APIRouter(prefix="/actions", tags=["actions"])


class CapabilityResponse(BaseModel):
    name: str
    label: str
    state: str
    read_only: bool
    summary: str


class FolderListRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=1, max_length=512)


class FolderListResponse(BaseModel):
    status: str
    summary: str
    entries: list[dict[str, str]] = Field(default_factory=list)
    truncated: bool = False


def _service(request: Request) -> CapabilityService:
    return cast(CapabilityService, request.app.state.capability_service)


@router.get("", response_model=list[CapabilityResponse])
async def list_actions(
    request: Request,
    _context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)],
) -> list[CapabilityResponse]:
    return [CapabilityResponse(name=item.name, label=item.label, state=item.state.value, read_only=item.read_only, summary=item.safe_summary) for item in _service(request).list()]


@router.post("/filesystem-list", response_model=FolderListResponse)
async def list_folder(
    payload: FolderListRequest,
    request: Request,
    context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)],
) -> FolderListResponse:
    result = await _service(request).list_folder(context, payload.target)
    raw_entries = result.data.get("entries", ())
    entries: list[dict[str, str]] = []
    if isinstance(raw_entries, tuple):
        for item in raw_entries:
            if isinstance(item, dict) and isinstance(item.get("name"), str) and isinstance(item.get("kind"), str):
                name = item["name"]
                kind = item["kind"]
                if isinstance(name, str) and isinstance(kind, str):
                    entries.append({"name": name, "kind": kind})
    return FolderListResponse(status=result.status.value, summary=result.safe_summary, entries=entries, truncated=result.data.get("truncated") is True)
