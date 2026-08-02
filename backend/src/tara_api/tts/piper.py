"""Safe, final-only Piper subprocess adapter with explicit local provisioning."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from tara_api.domain.tts import (
    SpeechFormat,
    SpeechLanguage,
    SpeechProviderReadiness,
    SpeechProviderState,
    SpeechSynthesisError,
    SpeechSynthesisFailure,
    SpeechSynthesisRequest,
    SpeechSynthesisResult,
    SpeechVoice,
)
from tara_api.tts.validation import validated_request, validated_result


class PiperProcess(Protocol):
    @property
    def returncode(self) -> int | None: ...

    async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    async def wait(self) -> int: ...


ProcessRunner = Callable[..., Awaitable[PiperProcess]]


async def _run_process(*args: str) -> PiperProcess:
    return await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


class PiperTextToSpeechProvider:
    """Map one validated request to raw PCM from a locally provisioned Piper voice."""

    name = "piper"
    streaming_supported = False

    def __init__(
        self,
        executable: str,
        voice_model_path: str,
        *,
        voice: SpeechVoice,
        output_format: SpeechFormat,
        voice_config_path: str | None = None,
        timeout_seconds: float = 30,
        process_runner: ProcessRunner = _run_process,
    ) -> None:
        if not executable or not voice_model_path or timeout_seconds <= 0:
            raise ValueError("invalid Piper configuration")
        if "\x00" in executable or "\x00" in voice_model_path or (voice_config_path is not None and "\x00" in voice_config_path):
            raise ValueError("invalid Piper path")
        self._executable = executable
        self._voice_model_path = Path(voice_model_path)
        self._voice_config_path = Path(voice_config_path) if voice_config_path else None
        self.voice = voice
        self._output_format = output_format
        self._timeout_seconds = timeout_seconds
        self._process_runner = process_runner
        self.supported_formats = (output_format,)
        self.supported_languages = (SpeechLanguage.ENGLISH, SpeechLanguage.HINDI, SpeechLanguage.MIXED)

    async def synthesize(self, request: SpeechSynthesisRequest) -> SpeechSynthesisResult:
        request = validated_request(request)
        self._validate_request(request)
        if not self._voice_model_path.is_file() or (self._voice_config_path is not None and not self._voice_config_path.is_file()):
            raise SpeechSynthesisFailure(SpeechSynthesisError.VOICE_NOT_AVAILABLE)
        process: PiperProcess | None = None
        started = time.monotonic()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                process = await self._process_runner(*self._arguments())
                audio, _stderr = await process.communicate(request.text.encode("utf-8"))
                if process.returncode not in {0, None}:
                    raise SpeechSynthesisFailure(SpeechSynthesisError.SYNTHESIS_FAILED)
        except asyncio.CancelledError:
            if process is not None:
                await self._terminate(process)
            raise
        except TimeoutError as error:
            if process is not None:
                await self._terminate(process)
            raise SpeechSynthesisFailure(SpeechSynthesisError.PROVIDER_TIMEOUT) from error
        except SpeechSynthesisFailure:
            raise
        except (FileNotFoundError, PermissionError, OSError) as error:
            raise SpeechSynthesisFailure(SpeechSynthesisError.PROVIDER_UNAVAILABLE) from error
        except Exception as error:
            raise SpeechSynthesisFailure(SpeechSynthesisError.SYNTHESIS_FAILED) from error
        return validated_result(request, audio, synthesis_duration_ms=max(0, round((time.monotonic() - started) * 1000)))

    async def readiness(self) -> SpeechProviderReadiness:
        if not self._voice_model_path.is_file() or (self._voice_config_path is not None and not self._voice_config_path.is_file()):
            return SpeechProviderReadiness(False, SpeechProviderState.UNAVAILABLE, SpeechSynthesisError.VOICE_NOT_AVAILABLE)
        executable_path = Path(self._executable)
        if executable_path.is_absolute() and not executable_path.is_file():
            return SpeechProviderReadiness(False, SpeechProviderState.UNAVAILABLE, SpeechSynthesisError.PROVIDER_UNAVAILABLE)
        return SpeechProviderReadiness(True, SpeechProviderState.READY)

    def _arguments(self) -> tuple[str, ...]:
        args = [self._executable, "--model", os.fspath(self._voice_model_path), "--output_raw"]
        if self._voice_config_path is not None:
            args.extend(("--config", os.fspath(self._voice_config_path)))
        return tuple(args)

    def _validate_request(self, request: SpeechSynthesisRequest) -> None:
        if request.voice != self.voice:
            raise SpeechSynthesisFailure(SpeechSynthesisError.VOICE_NOT_AVAILABLE)
        if request.language not in self.supported_languages:
            raise SpeechSynthesisFailure(SpeechSynthesisError.LANGUAGE_NOT_SUPPORTED)
        if request.output_format not in self.supported_formats:
            raise SpeechSynthesisFailure(SpeechSynthesisError.FORMAT_NOT_SUPPORTED)

    @staticmethod
    async def _terminate(process: PiperProcess) -> None:
        if process.returncode is not None:
            return
        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=1)
        except (OSError, TimeoutError):
            try:
                process.kill()
                await asyncio.wait_for(process.wait(), timeout=1)
            except (OSError, TimeoutError):
                return
