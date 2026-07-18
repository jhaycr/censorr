"""Pydantic models for native Sonarr/Radarr webhook payloads.

Shapes extracted from the Arr webhook source (see research/arr-webhook-
schemas.md). Everything censorr doesn't need is omitted and tolerated via
extra="ignore", so Arr version drift never breaks parsing. JSON is
camelCase; fields here use pydantic aliases.
"""

from pydantic import BaseModel, ConfigDict, Field


class ArrModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class WebhookMovie(ArrModel):
    title: str | None = None
    year: int | None = None
    folder_path: str | None = Field(default=None, alias="folderPath")
    tags: list[str] = []


class WebhookMovieFile(ArrModel):
    path: str | None = None
    relative_path: str | None = Field(default=None, alias="relativePath")


class WebhookSeries(ArrModel):
    title: str | None = None
    path: str | None = None
    tags: list[str] = []


class WebhookEpisodeFile(ArrModel):
    path: str | None = None
    relative_path: str | None = Field(default=None, alias="relativePath")


class RadarrWebhookPayload(ArrModel):
    event_type: str = Field(alias="eventType")
    instance_name: str | None = Field(default=None, alias="instanceName")
    movie: WebhookMovie | None = None
    movie_file: WebhookMovieFile | None = Field(default=None, alias="movieFile")
    is_upgrade: bool = Field(default=False, alias="isUpgrade")
    deleted_files: list[WebhookMovieFile] = Field(default=[], alias="deletedFiles")


class SonarrWebhookPayload(ArrModel):
    event_type: str = Field(alias="eventType")
    instance_name: str | None = Field(default=None, alias="instanceName")
    series: WebhookSeries | None = None
    episode_file: WebhookEpisodeFile | None = Field(default=None, alias="episodeFile")
    is_upgrade: bool = Field(default=False, alias="isUpgrade")
    deleted_files: list[WebhookEpisodeFile] = Field(default=[], alias="deletedFiles")


class JobSubmission(BaseModel):
    path: str
    preset: str | None = None
    force: bool = False
