import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from tara_api.stt.faster_whisper import FasterWhisperSpeechToTextProvider, FasterWhisperUnavailableError


class Model:
    calls = 0
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        type(self).calls += 1


def module_loader(_name: str) -> SimpleNamespace:
    return SimpleNamespace(WhisperModel=Model)


async def test_loading_is_lazy_once_and_requires_local_directory(tmp_path: Path) -> None:
    provider = FasterWhisperSpeechToTextProvider("local-model", "cpu", "int8", local_model_directory=str(tmp_path), module_loader=module_loader)  # type: ignore[arg-type]
    assert not await provider.readiness()
    await asyncio.gather(provider.load(), provider.load())
    assert Model.calls == 1
    assert await provider.readiness()


async def test_missing_dependency_and_missing_model_are_safe(tmp_path: Path) -> None:
    missing = FasterWhisperSpeechToTextProvider("local", "cpu", "int8", local_model_directory=str(tmp_path), module_loader=lambda _name: (_ for _ in ()).throw(ModuleNotFoundError()))  # type: ignore[arg-type]
    with pytest.raises(FasterWhisperUnavailableError):
        await missing.load()
    absent = FasterWhisperSpeechToTextProvider("local", "cpu", "int8")
    with pytest.raises(FasterWhisperUnavailableError):
        await absent.load()


def test_auto_download_and_invalid_combinations_are_rejected() -> None:
    with pytest.raises(ValueError):
        FasterWhisperSpeechToTextProvider("model", "cpu", "int8", auto_download=True)
    with pytest.raises(ValueError):
        FasterWhisperSpeechToTextProvider("model", "invalid", "int8")
