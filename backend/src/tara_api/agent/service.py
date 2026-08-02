"""Framework-independent, single-pass M9C text-agent application service."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from tara_api.agent.registry import AgentJob, AgentRequestRegistry
from tara_api.agent.validation import DefaultModelResponseValidator
from tara_api.domain.agent import (
    AgentError,
    AgentInputSource,
    AgentPersistenceStore,
    AgentRequest,
    AgentResponse,
    AgentSessionValidator,
    AgentState,
    AgentSubmission,
    ContextRequest,
    IntentCategory,
    IntentRoute,
    IntentRouter,
    LanguageModelProvider,
    ModelProviderFailure,
    ModelRequest,
    PromptBuilder,
    StructuredContextProvider,
)
from tara_api.domain.auth import AuthenticatedOwnerContext


class AgentServiceFailure(RuntimeError):
    """Stable code and sanitized message for a rejected service operation."""

    def __init__(self, code: AgentError) -> None:
        super().__init__("The request could not be completed.")
        self.code = code


class AgentService:
    """One route, context, prompt, and final-only model call per accepted request."""

    def __init__(
        self,
        *,
        registry: AgentRequestRegistry,
        persistence: AgentPersistenceStore,
        session_validator: AgentSessionValidator,
        router: IntentRouter,
        context_provider: Callable[[object], StructuredContextProvider],
        prompt_builder: PromptBuilder,
        model_provider: LanguageModelProvider | None,
        context_token_budget: int,
        output_token_budget: int,
        timeout_seconds: float,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if context_token_budget < 1 or output_token_budget < 1 or timeout_seconds <= 0:
            raise ValueError("invalid agent service configuration")
        self._registry = registry
        self._persistence = persistence
        self._session_validator = session_validator
        self._router = router
        self._context_provider = context_provider
        self._prompt_builder = prompt_builder
        self._model_provider = model_provider
        self._context_token_budget = context_token_budget
        self._output_token_budget = output_token_budget
        self._timeout_seconds = timeout_seconds
        self._now = now
        self._response_validator = DefaultModelResponseValidator()

    async def submit(
        self,
        context: AuthenticatedOwnerContext,
        submission: AgentSubmission,
        *,
        connection_id: UUID | None = None,
    ) -> AgentResponse:
        if not await self._session_validator.is_owner_session_active(context.owner.id, context.session.id):
            raise AgentServiceFailure(AgentError.SESSION_INVALIDATED)
        conversation_id = await self._resolve_conversation(context, submission)
        request = AgentRequest(
            uuid4(),
            uuid4(),
            context.owner.id,
            context.session.id,
            connection_id,
            submission.source,
            submission.text,
            self._utc_now(),
            conversation_id,
            submission.source_transcript_id,
            self._idempotency_hash(submission),
        )
        try:
            return await self._registry.submit(request, self._execute)
        except ValueError as error:
            raise AgentServiceFailure(self._error_from_value(error)) from error

    async def submit_final_transcript(
        self,
        context: AuthenticatedOwnerContext,
        text: str,
        transcript_id: UUID,
        *,
        conversation_id: UUID | None = None,
        connection_id: UUID | None = None,
    ) -> AgentResponse:
        return await self.submit(
            context,
            AgentSubmission(text, AgentInputSource.FINAL_TRANSCRIPT, conversation_id=conversation_id, source_transcript_id=transcript_id),
            connection_id=connection_id,
        )

    async def submit_partial_transcript(self, _context: AuthenticatedOwnerContext, _text: str) -> None:
        """Partial transcript data intentionally never creates an M9C request."""

        return None

    async def cancel(
        self,
        context: AuthenticatedOwnerContext,
        request_id: UUID,
        *,
        connection_id: UUID | None = None,
    ) -> bool:
        if not await self._session_validator.is_owner_session_active(context.owner.id, context.session.id):
            return False
        request = await self._registry.get_request(request_id, context.owner.id, context.session.id, connection_id)
        if request is None:
            return False
        canceled = await self._registry.cancel(request_id, context.owner.id, context.session.id, connection_id)
        if canceled:
            await self._safe_record_terminal(request, AgentState.CANCELED, AgentError.REQUEST_CANCELED)
        return canceled

    async def cancel_connection(self, connection_id: UUID) -> None:
        await self._registry.cancel_connection(connection_id)

    async def cancel_session(self, owner_id: UUID, session_id: UUID) -> None:
        await self._registry.cancel_session(owner_id, session_id)

    async def shutdown(self) -> None:
        await self._registry.shutdown()

    async def _execute(self, job: AgentJob) -> AgentResponse:
        request = job.request
        if not await self._session_validator.is_owner_session_active(request.owner_id, request.session_id):
            return await self._terminal(request, AgentState.FAILED, AgentError.SESSION_INVALIDATED)
        if not await self._persistence.record_accepted(request):
            return await self._terminal(request, AgentState.FAILED, AgentError.DUPLICATE_REQUEST)
        try:
            async with asyncio.timeout(self._timeout_seconds):
                await self._registry.transition(request.request_id, AgentState.ROUTING)
                route = self._router.classify(request.text)
                if route.category == IntentCategory.AMBIGUOUS:
                    return await self._deterministic(request, route.clarification or "Could you clarify your request?", route, AgentError.AMBIGUOUS_INTENT)
                if route.category == IntentCategory.UNSUPPORTED:
                    return await self._deterministic(request, "That capability is not available.", route, AgentError.UNSUPPORTED_INTENT)
                if route.category == IntentCategory.CONSEQUENTIAL_ACTION_REQUEST:
                    return await self._deterministic(request, "Action execution is not enabled yet.", route, AgentError.CONSEQUENTIAL_ACTION_NOT_ENABLED)
                if self._model_provider is None:
                    return await self._terminal(request, AgentState.FAILED, AgentError.PROVIDER_NOT_CONFIGURED, route=route)
                await self._registry.transition(request.request_id, AgentState.RETRIEVING_CONTEXT)
                context = await self._context_provider(request.owner_id).get_context(ContextRequest(request.owner_id, request.conversation_id))
                prompt = self._prompt_builder.build(request.text, context, model_context_token_budget=self._context_token_budget)
                await self._registry.transition(request.request_id, AgentState.GENERATING)
                model_response = self._response_validator.validate(
                    await self._model_provider.generate(
                        ModelRequest(request.request_id, prompt.messages, self._context_token_budget, self._output_token_budget, self._utc_now())
                    )
                )
                response = AgentResponse(request.request_id, model_response.text, AgentState.COMPLETED, self._utc_now(), route=route)
                await self._persistence.record_completed(
                    request,
                    response,
                    provider_name=self._model_provider.name,
                    model_identifier=model_response.model_identifier,
                    usage=model_response.usage,
                    duration_ms=model_response.duration_ms,
                )
                return response
        except asyncio.CancelledError:
            await self._safe_record_terminal(request, AgentState.CANCELED, AgentError.REQUEST_CANCELED)
            raise
        except TimeoutError:
            return await self._terminal(request, AgentState.TIMED_OUT, AgentError.REQUEST_TIMED_OUT)
        except ModelProviderFailure as error:
            return await self._terminal(request, AgentState.FAILED, error.code)
        except ValueError as error:
            return await self._terminal(request, AgentState.FAILED, self._error_from_value(error))
        except Exception:
            return await self._terminal(request, AgentState.FAILED, AgentError.INTERNAL_AGENT_ERROR)

    async def _deterministic(self, request: AgentRequest, text: str, route: IntentRoute, error: AgentError) -> AgentResponse:
        response = AgentResponse(request.request_id, text, AgentState.COMPLETED, self._utc_now(), error=error, route=route)
        await self._persistence.record_completed(request, response, provider_name=None, model_identifier=None, usage=None, duration_ms=None)
        return response

    async def _terminal(self, request: AgentRequest, state: AgentState, error: AgentError, *, route: IntentRoute | None = None) -> AgentResponse:
        await self._safe_record_terminal(request, state, error)
        return AgentResponse(request.request_id, "The request could not be completed.", state, self._utc_now(), error=error, route=route)

    async def _safe_record_terminal(self, request: AgentRequest, state: AgentState, error: AgentError) -> None:
        try:
            await self._persistence.record_terminal(request, state, error)
        except Exception:
            return None

    async def _resolve_conversation(self, context: AuthenticatedOwnerContext, submission: AgentSubmission) -> UUID:
        try:
            return await self._persistence.resolve_conversation(context.owner.id, submission.conversation_id)
        except Exception as error:
            raise AgentServiceFailure(AgentError.CONVERSATION_NOT_FOUND) from error

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise ValueError("agent clock must return UTC")
        return value.astimezone(UTC)

    @staticmethod
    def _idempotency_hash(submission: AgentSubmission) -> str:
        value = submission.idempotency_key or f"transcript:{submission.source_transcript_id}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _error_from_value(error: ValueError) -> AgentError:
        try:
            return AgentError(str(error))
        except ValueError:
            return AgentError.INTERNAL_AGENT_ERROR
