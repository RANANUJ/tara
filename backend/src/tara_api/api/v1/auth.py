"""Typed M4 owner bootstrap and bearer-session routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from tara_api.auth.service import AuthenticationError, AuthenticationService, BootstrapClosedError
from tara_api.domain.auth import AuthenticatedOwnerContext

router = APIRouter(prefix="/auth", tags=["auth"])


class CredentialsRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=1, max_length=128)
    client_label: str | None = Field(default=None, max_length=128)


class BootstrapStatusResponse(BaseModel):
    bootstrap_required: bool


class SessionResponse(BaseModel):
    owner_id: str
    email: str
    session_id: str
    expires_at: str
    token: str | None = None


def _service(request: Request) -> AuthenticationService:
    return request.app.state.authentication_service


async def authenticated_context(request: Request, authorization: Annotated[str | None, Header()] = None) -> AuthenticatedOwnerContext:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
    token = authorization.removeprefix("Bearer ").strip()
    if not token or " " in token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
    try:
        return await _service(request).authenticate(token)
    except AuthenticationError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required") from error


def _response(context: AuthenticatedOwnerContext, token: str | None = None) -> SessionResponse:
    return SessionResponse(owner_id=str(context.owner.id), email=context.owner.email, session_id=str(context.session.id), expires_at=context.session.expires_at.isoformat(), token=token)


@router.get("/bootstrap/status", response_model=BootstrapStatusResponse)
async def bootstrap_status(request: Request) -> BootstrapStatusResponse:
    return BootstrapStatusResponse(bootstrap_required=await _service(request).bootstrap_required())


@router.post("/bootstrap", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def bootstrap(payload: CredentialsRequest, request: Request) -> SessionResponse:
    try:
        await _service(request).bootstrap(payload.email, payload.password)
        owner, session, token = await _service(request).login(payload.email, payload.password, payload.client_label)
    except (BootstrapClosedError, ValueError):
        raise HTTPException(status.HTTP_409_CONFLICT, "bootstrap is unavailable") from None
    return _response(AuthenticatedOwnerContext(owner, session), token)


@router.post("/login", response_model=SessionResponse)
async def login(payload: CredentialsRequest, request: Request) -> SessionResponse:
    try:
        owner, session, token = await _service(request).login(payload.email, payload.password, payload.client_label)
    except AuthenticationError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication failed") from None
    return _response(AuthenticatedOwnerContext(owner, session), token)


@router.get("/session", response_model=SessionResponse)
async def current_session(context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)]) -> SessionResponse:
    return _response(context)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)]) -> None:
    await _service(request).logout(context)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(request: Request, context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)]) -> None:
    await _service(request).logout_all(context)


@router.get("/sessions", response_model=list[SessionResponse])
async def sessions(request: Request, context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)]) -> list[SessionResponse]:
    records = await request.app.state.authentication_store.list_for_owner(context.owner.id)
    return [SessionResponse(owner_id=str(context.owner.id), email=context.owner.email, session_id=str(record.id), expires_at=record.expires_at.isoformat()) for record in records]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(session_id: UUID, request: Request, context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)]) -> None:
    await request.app.state.authentication_store.revoke(context.owner.id, session_id, request.app.state.authentication_service._now())
