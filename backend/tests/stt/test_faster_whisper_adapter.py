import threading
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tara_api.domain.stt import TranscriptionRequest
from tara_api.stt.faster_whisper import FasterWhisperSpeechToTextProvider, FasterWhisperUnavailableError


class Segment:
    def __init__(self, start: float, end: float, text: str) -> None:
        self.start, self.end, self.text = start, end, text


class Model:
    thread_id: int | None = None
    def __init__(self, *_args: object, **_kwargs: object) -> None: pass
    def transcribe(self, _samples: list[float], **_kwargs: object) -> tuple[list[Segment], SimpleNamespace]:
        type(self).thread_id = threading.get_ident()
        return [Segment(0, 0.2, " hello"), Segment(0.2, 0.4, "world")], SimpleNamespace(language="hi", language_probability=0.8)


def loader(_name: str) -> SimpleNamespace:
    return SimpleNamespace(WhisperModel=Model)


def request() -> TranscriptionRequest:
    return TranscriptionRequest(uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), b"\0\0" * 640, datetime.now(UTC))


async def test_final_result_mapping_runs_off_event_loop(tmp_path: Path) -> None:
    provider = FasterWhisperSpeechToTextProvider("local", "cpu", "int8", local_model_directory=str(tmp_path), module_loader=loader)  # type: ignore[arg-type]
    session = await provider.start(request())
    result = [item async for item in session.results()][0]
    assert result.text == "hello world"
    assert result.language.code == "hi"
    assert result.language.confidence == 0.8
    assert [(item.start_ms, item.end_ms) for item in result.segments] == [(0, 200), (200, 400)]
    assert Model.thread_id != threading.get_ident()


async def test_invalid_result_and_cancellation_are_safe(tmp_path: Path) -> None:
    class BrokenModel(Model):
        def transcribe(self, *_args: object, **_kwargs: object) -> tuple[list[Segment], SimpleNamespace]:
            return [], SimpleNamespace(language="en")
    provider = FasterWhisperSpeechToTextProvider("local", "cpu", "int8", local_model_directory=str(tmp_path), module_loader=lambda _name: SimpleNamespace(WhisperModel=BrokenModel))  # type: ignore[arg-type]
    session = await provider.start(request())
    with pytest.raises(FasterWhisperUnavailableError):
        _ = [item async for item in session.results()]
