"""Environment-backed settings for the Tara backend bootstrap."""

import base64
import binascii
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from tara_api.domain.wakeword import WakeWordConfiguration

Environment = Literal["development", "test", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    """Load non-product configuration from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="TARA_",
        extra="ignore",
    )

    app_name: str = "Tara API"
    app_version: str = "0.1.0"
    build_revision: str | None = None
    environment: Environment = "development"
    log_level: LogLevel = "INFO"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    database_url: str = "sqlite+aiosqlite:///./data/tara.db"
    database_encryption_key: SecretStr = SecretStr("")
    backup_directory: str = "./data/backups"
    service_secret: SecretStr = SecretStr("")
    task_payload_encryption_key: SecretStr = SecretStr("")
    session_absolute_minutes: int = Field(default=1440, ge=5, le=10080)
    session_idle_minutes: int = Field(default=60, ge=5, le=1440)
    health_check_timeout_ms: int = Field(default=1000, ge=10, le=10000)
    websocket_ticket_seconds: int = Field(default=60, ge=10, le=300)
    websocket_hello_seconds: int = Field(default=10, ge=1, le=60)
    websocket_idle_seconds: int = Field(default=120, ge=10, le=3600)
    websocket_session_check_seconds: int = Field(default=15, ge=1, le=300)
    websocket_max_message_bytes: int = Field(default=16384, ge=512, le=1048576)
    websocket_max_connections_per_session: int = Field(default=3, ge=1, le=20)
    websocket_max_events_per_second: int = Field(default=30, ge=1, le=300)
    websocket_max_outgoing_queue: int = Field(default=32, ge=1, le=256)
    stt_provider: Literal["fake", "faster_whisper", "disabled"] = "fake"
    stt_model: str = "small"
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"
    stt_timeout_seconds: int = Field(default=30, ge=1, le=300)
    stt_max_queued_jobs: int = Field(default=8, ge=1, le=64)
    stt_max_concurrent_jobs: int = Field(default=1, ge=1, le=4)
    stt_required: bool = False
    stt_health_timeout_ms: int = Field(default=500, ge=10, le=10000)
    stt_language_hint: Literal["en", "hi"] | None = None
    stt_partial_mode: Literal["provider", "final_only"] = "provider"
    stt_local_model_directory: str | None = None
    tts_provider: Literal["fake", "piper", "elevenlabs", "disabled"] = "disabled"
    tts_required: bool = False
    tts_max_text_characters: int = Field(default=4000, ge=1, le=4000)
    tts_max_audio_bytes: int = Field(default=8 * 1024 * 1024, ge=1024, le=8 * 1024 * 1024)
    tts_timeout_seconds: int = Field(default=30, ge=1, le=300)
    tts_max_queued_requests: int = Field(default=8, ge=1, le=64)
    tts_max_concurrent_requests: int = Field(default=1, ge=1, le=8)
    tts_max_requests_per_connection: int = Field(default=2, ge=1, le=16)
    tts_max_requests_per_session: int = Field(default=4, ge=1, le=32)
    tts_max_requests_per_owner: int = Field(default=8, ge=1, le=64)
    tts_max_chunk_bytes: int = Field(default=8 * 1024, ge=2, le=64 * 1024)
    tts_max_terminal_records: int = Field(default=32, ge=1, le=256)
    tts_terminal_retention_seconds: int = Field(default=300, ge=1, le=3600)
    tts_max_retained_audio_bytes: int = Field(default=32 * 1024 * 1024, ge=1024, le=64 * 1024 * 1024)
    tts_delivery_timeout_seconds: int = Field(default=5, ge=1, le=60)
    tts_output_encoding: Literal["pcm_s16le"] = "pcm_s16le"
    tts_output_sample_rate: Literal[16000, 22050, 24000] = 22050
    tts_output_channels: Literal[1] = 1
    tts_language_mode: Literal["auto", "en", "hi", "mixed"] = "auto"
    tts_voice_identifier: str = ""
    tts_piper_executable: str = ""
    tts_piper_voice_model_path: str | None = None
    tts_piper_voice_config_path: str | None = None
    elevenlabs_api_key: SecretStr = SecretStr("")
    elevenlabs_model: str = ""
    wakeword_provider: Literal["fake", "disabled"] = "disabled"
    wakeword_enabled: bool = False
    wakeword_required: bool = False
    wakeword_phrase: str = "tara"
    wakeword_confidence_threshold: float = Field(default=0.85, ge=0, le=1)
    wakeword_minimum_consecutive_detections: int = Field(default=2, ge=1, le=10)
    wakeword_cooldown_seconds: float = Field(default=3, ge=0, le=60)
    wakeword_debounce_seconds: float = Field(default=1, ge=0, le=10)
    wakeword_frame_duration_ms: int = Field(default=20, ge=1, le=1000)
    wakeword_maximum_buffered_frames: int = Field(default=8, ge=1, le=128)
    wakeword_language_mode: Literal["auto", "en", "hi", "mixed"] = "auto"
    wakeword_foreground_only: bool = True
    wakeword_maximum_frame_age_seconds: float = Field(default=2, gt=0, le=30)
    wakeword_timeout_seconds: float = Field(default=2, ge=1, le=30)
    memory_semantic_provider: Literal["chromadb", "disabled"] = "disabled"
    memory_chroma_directory: str = "./data/chroma"
    memory_scheduler_enabled: bool = True
    scheduler_enabled: bool = False
    scheduler_poll_seconds: float = Field(default=5, ge=0.1, le=300)
    scheduler_due_batch_size: int = Field(default=8, ge=1, le=64)
    scheduler_max_concurrent_runs: int = Field(default=2, ge=1, le=8)
    scheduler_max_runs_per_owner: int = Field(default=1, ge=1, le=8)
    scheduler_claim_lease_seconds: int = Field(default=60, ge=1, le=300)
    scheduler_run_timeout_seconds: int = Field(default=30, ge=1, le=300)
    scheduler_cleanup_interval_seconds: int = Field(default=300, ge=10, le=3600)
    scheduler_cleanup_batch_size: int = Field(default=32, ge=1, le=256)
    scheduler_payload_retention_hours: int = Field(default=24, ge=1, le=24 * 365)
    scheduler_run_retention_days: int = Field(default=30, ge=1, le=365)
    scheduler_shutdown_timeout_seconds: int = Field(default=10, ge=1, le=60)
    tools_filesystem_read_enabled: bool = False
    tools_filesystem_read_roots: tuple[str, ...] = ()
    fake_consequential_enabled: bool = False
    fake_consequential_uncertain: bool = False
    llm_provider: Literal["fake", "ollama", "disabled"] = "disabled"
    llm_required: bool = False
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = ""
    ollama_fast_model: str = ""
    ollama_reasoning_model: str = ""
    llm_timeout_seconds: int = Field(default=30, ge=1, le=300)
    llm_context_token_budget: int = Field(default=4096, ge=128, le=32768)
    llm_output_token_budget: int = Field(default=512, ge=1, le=8192)
    llm_temperature: float = Field(default=0.2, ge=0, le=1)
    llm_streaming: bool = False
    agent_intent_confidence_threshold: float = Field(default=0.75, gt=0, le=1)
    agent_context_memory_limit: int = Field(default=8, ge=1, le=100)
    agent_context_recent_turn_limit: int = Field(default=8, ge=1, le=100)
    agent_context_memory_item_char_limit: int = Field(default=512, ge=1, le=4096)
    agent_context_recent_turn_char_limit: int = Field(default=768, ge=1, le=4096)
    agent_context_total_char_limit: int = Field(default=4096, ge=1, le=12000)
    agent_context_estimated_token_limit: int = Field(default=1024, ge=1, le=4096)
    agent_context_allowed_sensitivities: tuple[Literal["normal", "private", "sensitive", "restricted"], ...] = ("normal",)
    agent_request_timeout_seconds: int = Field(default=30, ge=1, le=300)
    agent_max_tool_iterations: int = Field(default=2, ge=1, le=4)
    agent_max_queued_requests: int = Field(default=8, ge=1, le=64)
    agent_max_concurrent_requests: int = Field(default=1, ge=1, le=8)
    agent_max_requests_per_connection: int = Field(default=2, ge=1, le=16)
    agent_max_requests_per_session: int = Field(default=4, ge=1, le=32)
    agent_max_requests_per_owner: int = Field(default=8, ge=1, le=64)
    agent_max_terminal_records: int = Field(default=32, ge=1, le=256)
    agent_terminal_retention_seconds: int = Field(default=300, ge=1, le=3600)

    @model_validator(mode="after")
    def validate_stt(self) -> "Settings":
        if self.environment == "production" and self.stt_provider == "fake":
            raise ValueError("production cannot use the fake STT provider")
        if self.stt_required and self.stt_provider == "disabled":
            raise ValueError("required STT cannot be disabled")
        if self.environment == "production" and self.tts_provider == "fake":
            raise ValueError("production cannot use the fake TTS provider")
        if self.tts_required and self.tts_provider == "disabled":
            raise ValueError("required TTS cannot be disabled")
        if self.tts_provider == "piper" and (not self.tts_piper_executable or not self.tts_piper_voice_model_path or not self.tts_voice_identifier):
            raise ValueError("Piper TTS requires an executable, explicit local voice model, and voice identifier")
        if self.tts_piper_voice_config_path and self.tts_provider != "piper":
            raise ValueError("Piper voice configuration requires the Piper provider")
        if self.tts_provider == "elevenlabs" and (not self.elevenlabs_api_key.get_secret_value() or not self.tts_voice_identifier or not self.elevenlabs_model):
            raise ValueError("ElevenLabs TTS requires a server API key, voice identifier, and model")
        if self.tts_max_concurrent_requests > self.tts_max_queued_requests:
            raise ValueError("TTS concurrency cannot exceed queued request capacity")
        if self.tts_max_requests_per_connection > self.tts_max_requests_per_session:
            raise ValueError("connection TTS request limit cannot exceed session request limit")
        if self.tts_max_requests_per_session > self.tts_max_requests_per_owner:
            raise ValueError("session TTS request limit cannot exceed owner request limit")
        if self.tts_max_chunk_bytes % (self.tts_output_channels * 2):
            raise ValueError("TTS chunk bytes must align to the output frame size")
        if self.tts_max_retained_audio_bytes < self.tts_max_audio_bytes:
            raise ValueError("TTS retained-audio budget must allow one valid result")
        if self.environment == "production" and self.wakeword_provider == "fake":
            raise ValueError("production cannot use the fake wake-word provider")
        if self.wakeword_enabled and self.wakeword_provider == "disabled":
            raise ValueError("enabled wake word requires a configured provider")
        if self.wakeword_required and self.wakeword_provider == "disabled":
            raise ValueError("required wake word cannot be disabled")
        if self.memory_semantic_provider == "chromadb" and not self.memory_chroma_directory.strip():
            raise ValueError("ChromaDB requires an explicit local directory")
        if self.scheduler_max_runs_per_owner > self.scheduler_max_concurrent_runs:
            raise ValueError("scheduler owner concurrency cannot exceed global concurrency")
        if self.scheduler_enabled:
            try:
                key = base64.b64decode(self.task_payload_encryption_key.get_secret_value(), validate=True)
            except (ValueError, binascii.Error) as error:
                raise ValueError("scheduler requires a valid task payload encryption key") from error
            if len(key) != 32:
                raise ValueError("scheduler requires a 32-byte task payload encryption key")
        if self.tools_filesystem_read_enabled and not self.tools_filesystem_read_roots:
            raise ValueError("filesystem read requires at least one allowlisted root")
        if self.environment == "production" and self.fake_consequential_enabled:
            raise ValueError("production cannot enable the fake consequential action")
        WakeWordConfiguration(
            provider=self.wakeword_provider,
            phrase=self.wakeword_phrase,
            enabled=self.wakeword_enabled,
            confidence_threshold=self.wakeword_confidence_threshold,
            minimum_consecutive_detections=self.wakeword_minimum_consecutive_detections,
            cooldown_seconds=self.wakeword_cooldown_seconds,
            debounce_seconds=self.wakeword_debounce_seconds,
            frame_duration_ms=self.wakeword_frame_duration_ms,
            maximum_buffered_frames=self.wakeword_maximum_buffered_frames,
            language_mode=self.wakeword_language_mode,
            foreground_only=self.wakeword_foreground_only,
            maximum_frame_age_seconds=self.wakeword_maximum_frame_age_seconds,
        )
        if self.environment == "production" and self.llm_provider == "fake":
            raise ValueError("production cannot use the fake language-model provider")
        if self.llm_required and self.llm_provider == "disabled":
            raise ValueError("required language-model provider cannot be disabled")
        parsed_ollama_url = urlsplit(self.ollama_base_url)
        if parsed_ollama_url.scheme not in {"http", "https"} or not parsed_ollama_url.hostname or parsed_ollama_url.username or parsed_ollama_url.password:
            raise ValueError("invalid Ollama base URL")
        if self.llm_provider == "ollama" and not (self.ollama_model or self.ollama_fast_model or self.ollama_reasoning_model):
            raise ValueError("Ollama provider requires a model identifier")
        if self.llm_streaming:
            raise ValueError("streaming language-model output is not implemented")
        if "restricted" in self.agent_context_allowed_sensitivities:
            raise ValueError("restricted context cannot be enabled")
        if self.agent_context_memory_item_char_limit > self.agent_context_total_char_limit:
            raise ValueError("memory context item limit exceeds the total context limit")
        if self.agent_context_recent_turn_char_limit > self.agent_context_total_char_limit:
            raise ValueError("recent-turn context item limit exceeds the total context limit")
        if self.agent_context_total_char_limit > self.agent_context_estimated_token_limit * 4:
            raise ValueError("context character limit exceeds the estimated token limit")
        if self.agent_max_concurrent_requests > self.agent_max_queued_requests:
            raise ValueError("agent concurrency cannot exceed queued request capacity")
        if self.agent_max_requests_per_connection > self.agent_max_requests_per_session:
            raise ValueError("connection request limit cannot exceed session request limit")
        if self.agent_max_requests_per_session > self.agent_max_requests_per_owner:
            raise ValueError("session request limit cannot exceed owner request limit")
        return self

    def secret_values(self) -> tuple[str, ...]:
        """Return configured secrets for log redaction without exposing them to callers."""
        return tuple(
            value
            for value in (
                self.service_secret.get_secret_value(),
                self.task_payload_encryption_key.get_secret_value(),
                self.elevenlabs_api_key.get_secret_value(),
            )
            if value
        )

    def logging_context(self) -> dict[str, object]:
        """Return settings suitable for structured logging after formatter redaction."""
        return {
            "app_name": self.app_name,
            "environment": self.environment,
            "log_level": self.log_level,
            "host": self.host,
            "port": self.port,
            "database_url": self.database_url,
            "service_secret": self.service_secret,
        }


@lru_cache
def get_settings() -> Settings:
    """Return cached process settings loaded from the environment."""
    return Settings()
