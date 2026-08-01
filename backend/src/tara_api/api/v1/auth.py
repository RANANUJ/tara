"""Typed M4 owner bootstrap and bearer-session routes."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, status
from pydantic import BaseModel, Field

from tara_api.auth.service import AuthenticationError, AuthenticationService, BootstrapClosedError
from tara_api.domain.auth import AuthenticatedOwnerContext
from tara_api.domain.errors import AuthenticationFailedError, AuthenticationRequiredError, ConflictError

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


class LoginSessionResponse(SessionResponse):
    token: str


def _service(request: Request) -> AuthenticationService:
    return cast(AuthenticationService, request.app.state.authentication_service)


async def authenticated_context(request: Request, authorization: Annotated[str | None, Header()] = None) -> AuthenticatedOwnerContext:
    if authorization is None or not authorization.startswith("Bearer "):
        raise AuthenticationRequiredError
    token = authorization.removeprefix("Bearer ").strip()
    if not token or " " in token:
        raise AuthenticationRequiredError
    try:
        return await _service(request).authenticate(token)
    except AuthenticationError as error:
        raise AuthenticationRequiredError from error


def _response(context: AuthenticatedOwnerContext) -> SessionResponse:
    return SessionResponse(owner_id=str(context.owner.id), email=context.owner.email, session_id=str(context.session.id), expires_at=context.session.expires_at.isoformat())


def _login_response(context: AuthenticatedOwnerContext, token: str) -> LoginSessionResponse:
    return LoginSessionResponse(owner_id=str(context.owner.id), email=context.owner.email, session_id=str(context.session.id), expires_at=context.session.expires_at.isoformat(), token=token)


@router.get("/bootstrap/status", response_model=BootstrapStatusResponse)
async def bootstrap_status(request: Request) -> BootstrapStatusResponse:
    return BootstrapStatusResponse(bootstrap_required=await _service(request).bootstrap_required())


@router.post("/bootstrap", response_model=LoginSessionResponse, status_code=status.HTTP_201_CREATED)
async def bootstrap(payload: CredentialsRequest, request: Request) -> LoginSessionResponse:
    try:
        await _service(request).bootstrap(payload.email, payload.password)
        owner, session, token = await _service(request).login(payload.email, payload.password, payload.client_label)
    except (BootstrapClosedError, ValueError):
        raise ConflictError("Bootstrap is unavailable.") from None
    return _login_response(AuthenticatedOwnerContext(owner, session), token)


@router.post("/login", response_model=LoginSessionResponse)
async def login(payload: CredentialsRequest, request: Request) -> LoginSessionResponse:
    try:
        owner, session, token = await _service(request).login(payload.email, payload.password, payload.client_label)
    except AuthenticationError:
        raise AuthenticationFailedError from None
    return _login_response(AuthenticatedOwnerContext(owner, session), token)


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
    records = await _service(request).list_sessions(context)
    return [SessionResponse(owner_id=str(context.owner.id), email=context.owner.email, session_id=str(record.id), expires_at=record.expires_at.isoformat()) for record in records]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(session_id: UUID, request: Request, context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)]) -> None:
    await _service(request).revoke_session(context, session_id)
