"""Optional faster-whisper adapter with explicit local-model loading."""

import asyncio
import importlib
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from tara_api.domain.stt import FinalTranscript, SpeechToTextSession, TranscriptionRequest, TranscriptLanguage, TranscriptSegment


class FasterWhisperUnavailableError(RuntimeError):
    """Safe provider-boundary failure; never expose its cause to clients."""


ModuleLoader = Callable[[str], ModuleType]


class _FinalOnlySession:
    def __init__(self, task: asyncio.Task[FinalTranscript]) -> None:
        self._task = task

    def results(self) -> AsyncIterator[FinalTranscript]:
        return self._results()

    async def _results(self) -> AsyncIterator[FinalTranscript]:
        yield await self._task

    async def cancel(self) -> None:
        self._task.cancel()


class FasterWhisperSpeechToTextProvider:
    """Final-turn adapter; real model work always runs outside the event loop."""

    name = "faster-whisper"

    def __init__(
        self,
        model: str,
        device: str,
        compute_type: str,
        *,
        language_hint: str | None = None,
        beam_size: int = 5,
        local_model_directory: str | None = None,
        auto_download: bool = False,
        module_loader: ModuleLoader = importlib.import_module,
    ) -> None:
        if not model or device not in {"cpu", "cuda", "auto"} or not compute_type or beam_size < 1:
            raise ValueError("invalid faster-whisper configuration")
        if language_hint is not None and language_hint not in {"en", "hi"}:
            raise ValueError("invalid language hint")
        if auto_download:
            raise ValueError("automatic model download is not supported")
        self._model_identifier = model
        self._device = device
        self._compute_type = compute_type
        self._language_hint = language_hint
        self._beam_size = beam_size
        self._local_model_directory = local_model_directory
        self._module_loader = module_loader
        self._model: Any | None = None
        self._load_lock = asyncio.Lock()

    async def readiness(self) -> bool:
        return self._model is not None

    async def load(self) -> None:
        if self._model is not None:
            return
        async with self._load_lock:
            if self._model is not None:
                return
            if self._local_model_directory is None or not Path(self._local_model_directory).is_dir():
                raise FasterWhisperUnavailableError("local model is not provisioned")
            try:
                module = self._module_loader("faster_whisper")
                model_class = module.WhisperModel
                self._model = await asyncio.to_thread(
                    model_class,
                    self._model_identifier,
                    device=self._device,
                    compute_type=self._compute_type,
                    download_root=self._local_model_directory,
                )
            except FasterWhisperUnavailableError:
                raise
            except Exception as error:
                raise FasterWhisperUnavailableError("model load failed") from error

    async def start(self, request: TranscriptionRequest) -> SpeechToTextSession:
        await self.load()
        task = asyncio.create_task(self._transcribe(request))
        return _FinalOnlySession(task)

    async def _transcribe(self, request: TranscriptionRequest) -> FinalTranscript:
        try:
            return await asyncio.to_thread(self._transcribe_blocking, request.pcm16)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            raise FasterWhisperUnavailableError("transcription failed") from error

    def _transcribe_blocking(self, pcm16: bytes) -> FinalTranscript:
        if not pcm16 or len(pcm16) % 2:
            raise ValueError("invalid audio")
        model = cast(Any, self._model)
        samples = [int.from_bytes(pcm16[index : index + 2], "little", signed=True) / 32768 for index in range(0, len(pcm16), 2)]
        segments, info = model.transcribe(samples, language=self._language_hint, beam_size=self._beam_size)
        mapped = tuple(TranscriptSegment(round(item.start * 1000), round(item.end * 1000), item.text.strip()) for item in segments if item.text.strip())
        if not mapped:
            raise ValueError("empty provider result")
        language = str(getattr(info, "language", "und"))
        probability = getattr(info, "language_probability", None)
        safe_language = language if language in {"en", "hi"} else "und"
        confidence = float(probability) if isinstance(probability, (float, int)) and 0 <= probability <= 1 else None
        return FinalTranscript(" ".join(segment.text for segment in mapped), TranscriptLanguage(safe_language, confidence), None, mapped)
