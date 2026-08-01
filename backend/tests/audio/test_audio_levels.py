"""Safe bounded audio-level tests."""

from tara_api.transport.audio import CANONICAL_FORMAT, AudioLevelMeter, pcm_rms_level


def test_audio_level_is_clamped_smoothed_and_throttled() -> None:
    meter = AudioLevelMeter(smoothing=0.5, emit_every_frames=2)
    assert meter.observe(0) is None
    value = meter.observe(2)
    assert value is not None and 0 < value < 1
    assert meter.observe(float("nan")) is None
    value = meter.observe(float("inf"))
    assert value is not None and 0 <= value <= 1


def test_pcm_rms_level_matches_known_silence_and_waveform() -> None:
    silence = bytes(CANONICAL_FORMAT.frame_bytes)
    waveform = (16384).to_bytes(2, "little", signed=True) * (CANONICAL_FORMAT.frame_bytes // 2)
    assert pcm_rms_level(silence) == 0
    assert 0.49 < pcm_rms_level(waveform) < 0.51
