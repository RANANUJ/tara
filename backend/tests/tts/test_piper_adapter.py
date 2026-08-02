import asyncio
from pathlib import Path

import pytest

from tara_api.domain.tts import SpeechFormat, SpeechSynthesisError, SpeechSynthesisFailure, SpeechVoice
from tara_api.tts.piper import PiperTextToSpeechProvider

from .conftest import request


class FakeProcess:
    def __init__(self, audio: bytes = b"\0\0" * 220, *, returncode: int | None = None, delay_seconds: float = 0) -> None:
        self.audio = audio
        self.returncode = returncode
        self.delay_seconds = delay_seconds
        self.stdin: bytes | None = None
        self.terminated = False

    async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
        self.stdin = input
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.returncode is None:
            self.returncode = 0
        return self.audio, b"sensitive stderr"

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15

    def kill(self) -> None:
        self.terminated = True
        self.returncode = -9

    async def wait(self) -> int:
        return self.returncode or 0


def provider(tmp_path: Path, process: FakeProcess, calls: list[tuple[str, ...]], *, timeout_seconds: float = 1) -> PiperTextToSpeechProvider:
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"model")

    async def runner(*args: str) -> FakeProcess:
        calls.append(args)
        return process

    return PiperTextToSpeechProvider("piper", str(model), voice=SpeechVoice("local-voice"), output_format=SpeechFormat(), timeout_seconds=timeout_seconds, process_runner=runner)


async def test_piper_uses_argument_array_and_maps_pcm(tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []
    process = FakeProcess()
    result = await provider(tmp_path, process, calls).synthesize(request())
    assert calls == [("piper", "--model", str(tmp_path / "voice.onnx"), "--output_raw")]
    assert process.stdin == b"Hello Tara"
    assert result.sample_count == 220


@pytest.mark.parametrize(
    ("process", "timeout", "code"),
    (
        (FakeProcess(returncode=1), 1, SpeechSynthesisError.SYNTHESIS_FAILED),
        (FakeProcess(audio=b"\0"), 1, SpeechSynthesisError.INVALID_AUDIO_METADATA),
        (FakeProcess(delay_seconds=1), 0.01, SpeechSynthesisError.PROVIDER_TIMEOUT),
    ),
)
async def test_piper_failures_are_sanitized(tmp_path: Path, process: FakeProcess, timeout: float, code: SpeechSynthesisError) -> None:
    with pytest.raises(SpeechSynthesisFailure) as error:
        await provider(tmp_path, process, [], timeout_seconds=timeout).synthesize(request())
    assert error.value.code is code
    assert "stderr" not in str(error.value)


async def test_piper_cancellation_terminates_child_and_missing_voice_is_safe(tmp_path: Path) -> None:
    process = FakeProcess(delay_seconds=1)
    item = provider(tmp_path, process, [])
    task = asyncio.create_task(item.synthesize(request()))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.terminated
    missing = PiperTextToSpeechProvider("piper", str(tmp_path / "missing.onnx"), voice=SpeechVoice("local-voice"), output_format=SpeechFormat())
    with pytest.raises(SpeechSynthesisFailure) as error:
        await missing.synthesize(request())
    assert error.value.code is SpeechSynthesisError.VOICE_NOT_AVAILABLE
