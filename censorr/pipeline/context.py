from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from censorr.audio.windows import MuteWindow
from censorr.config.schema import ResolvedConfig
from censorr.detect.matcher import Match
from censorr.media.probe import MediaInfo
from censorr.naming.models import NamingPlan
from censorr.pipeline.job import Job
from censorr.subtitles.io import SubtitleDoc
from censorr.subtitles.select import TrackSelection


class PipelineContext(BaseModel):
    """The stage contract (design §4). Each stage validates its own inputs
    are set and returns an updated copy; `outcome` short-circuits the
    remaining stages once a stage decides the job is done (R16 skip cases).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    job: Job
    cfg: ResolvedConfig
    mode: Literal["full", "clean", "subtitles_only"] = "full"
    outcome: str | None = None
    media_info: MediaInfo | None = None
    selection: TrackSelection | None = None
    subtitle_doc: SubtitleDoc | None = None
    matches: dict[int, list[Match]] = {}
    windows: list[MuteWindow] = []
    masked_doc: SubtitleDoc | None = None
    captions_doc: SubtitleDoc | None = None
    naming_plan: NamingPlan | None = None
    temp_output: Path | None = None
