from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict


class SectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DetectConfig(SectionModel):
    wordlist: Path | None = None
    buffer_s: float = 0.2
    fuzzy_threshold: int = 85


class SubtitlesConfig(SectionModel):
    language: str = "en"
    exclude_titles: list[str] = ["sdh", "hi", "cc"]
    mute_captions: bool = True
    allow_language_mismatch: bool = True


class AudioConfig(SectionModel):
    language: str = ""
    fallback_codec: str = "eac3"
    fallback_bitrate: str = "640k"
    target_codec: str | None = None


class NamingConfig(SectionModel):
    edition_tag: str = "Censorr"
    write_sidecar: bool = False
    sidecar_token: str = "censorr"  # noqa: S105 -- filename token, not a credential
    tv_clean_root: Path | None = None


class BehaviorConfig(SectionModel):
    on_clean_tv: Literal["publish", "skip"] = "publish"
    on_clean_movie: Literal["publish", "skip"] = "skip"
    fail_on_no_subtitles: bool = False


class QcConfig(SectionModel):
    audio_min_drop_db: float = -12.0
    max_mute_ratio: float = 0.05
    max_window_s: float = 15.0
    warn_matched_entry_ratio: float = 0.20
    warn_masked_entry_ratio: float = 0.15
    continue_on_audio_qc_fail: bool = False
    continue_on_subtitle_qc_fail: bool = False


class ServiceConfig(SectionModel):
    secret: str = ""
    queue_path: Path = Path("/app/queue")
    max_retries: int = 3
    lease_seconds: int = 1800
    failed_ttl_days: int = 7
    record_ttl_days: int = 30
    path_map: dict[str, str] = {}


# Dotted paths (within the merged preset/file dict) resolved against the
# config file's directory when given as relative strings (design §4).
RELATIVE_PATH_FIELDS = (
    ("detect", "wordlist"),
    ("naming", "tv_clean_root"),
    ("service", "queue_path"),
)


class ResolvedConfig(BaseModel):
    """The one-shot, fully-resolved config: CLI explicit > preset > file > defaults."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    detect: DetectConfig = DetectConfig()
    subtitles: SubtitlesConfig = SubtitlesConfig()
    audio: AudioConfig = AudioConfig()
    naming: NamingConfig = NamingConfig()
    behavior: BehaviorConfig = BehaviorConfig()
    qc: QcConfig = QcConfig()
    service: ServiceConfig = ServiceConfig()
    arr_tag_presets: dict[str, str] = {}
    preset: str | None = None
