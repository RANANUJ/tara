"""Authenticated M14 confirmation proposal and response transport."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from tara_api.api.v1.auth import authenticated_context
from tara_api.capabilities.consequential import ConsequentialAction, FakeConsequentialActionService
from tara_api.domain.auth import AuthenticatedOwnerContext

router = APIRouter(prefix="/confirmations", tags=["confirmations"])


class ProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str = Field(min_length=1, max_length=64)


class ResponseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response: str = Field(min_length=1, max_length=64)


class ActionResponse(BaseModel):
    action_id: str
    confirmation_id: str
    state: str


def _service(request: Request) -> FakeConsequentialActionService:
    return cast(FakeConsequentialActionService, request.app.state.fake_consequential_service)


def _response(action: ConsequentialAction) -> ActionResponse:
    return ActionResponse(action_id=str(action.id), confirmation_id=str(action.confirmation_id), state=action.state)


@router.post("/fake-consequential", response_model=ActionResponse)
async def propose(payload: ProposalRequest, request: Request, context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)]) -> ActionResponse:
    action = await _service(request).propose(context, payload.target)
    if action is None:
        return ActionResponse(action_id="", confirmation_id="", state="unavailable")
    return _response(action)


@router.post("/{confirmation_id}/respond", response_model=ActionResponse)
async def respond(confirmation_id: UUID, payload: ResponseRequest, request: Request, context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)]) -> ActionResponse:
    action = await _service(request).respond(context, confirmation_id, payload.response)
    if action is None:
        return ActionResponse(action_id="", confirmation_id="", state="not_found")
    return _response(action)
