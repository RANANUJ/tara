"""M11A adapter from validated M7 foreground audio frames."""

from datetime import datetime

from tara_api.domain.audio import AudioFrame
from tara_api.domain.wakeword import WakeWordAudioFrame, WakeWordError, WakeWordFailure, WakeWordSessionIdentity


def from_m7_audio_frame(identity: WakeWordSessionIdentity, frame: AudioFrame, captured_at: datetime) -> WakeWordAudioFrame:
    """Convert an already-validated M7 frame without retaining its PCM payload."""
    if frame.audio_session_id != identity.audio_session_id:
        raise WakeWordFailure(WakeWordError.STALE_AUDIO_SESSION)
    return WakeWordAudioFrame(
        sequence=frame.sequence,
        pcm16=frame.payload,
        sample_rate=16000,
        sample_width_bytes=2,
        channels=1,
        duration_ms=20,
        captured_at=captured_at,
    )
