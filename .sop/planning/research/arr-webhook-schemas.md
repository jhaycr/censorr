# Research: Sonarr/Radarr Webhook Schemas — Exhaustive (from source)

Extracted 2026-07-15 directly from the `develop` branches of Sonarr and Radarr (`src/NzbDrone.Core/Notifications/Webhook/*.cs`). These are the authoritative shapes for v2's pydantic models. JSON serialization is camelCase.

## Event types

Sonarr `WebhookEventType`: `Test, Grab, Download, Rename, SeriesAdd, SeriesDelete, EpisodeFileDelete, Health, ApplicationUpdate, HealthRestored, ManualInteractionRequired`. (Radarr's is analogous with movie variants: `MovieAdded`, `MovieFileDelete`, `MovieDelete`, etc.)

**v2 policy**: process `Download` (covers both new import and upgrade — check `isUpgrade`); `Test` → 200 success without enqueue; everything else → 200 `{status: ignored}`.

## Sonarr `Download` payload (WebhookImportPayload)

Common base (all payloads): `eventType`, `instanceName`, `applicationUrl`.

| Field | Type |
|---|---|
| `series` | WebhookSeries |
| `episodes` | WebhookEpisode[] |
| `episodeFile` | WebhookEpisodeFile |
| `isUpgrade` | bool |
| `downloadClient` / `downloadClientType` / `downloadId` | string |
| `deletedFiles` | WebhookEpisodeFile[] (upgrades) |
| `customFormatInfo`, `release` | objects (ignore) |

**WebhookSeries**: `id, title, titleSlug, path, tvdbId, tvMazeId, tmdbId, imdbId, type, year, genres[], images[], tags[] (label strings), originalLanguage`.

**WebhookEpisode**: `id, episodeNumber, seasonNumber, title, overview, airDate, airDateUtc, seriesId, tvdbId`.

**WebhookEpisodeFile**: `id, relativePath, path, quality, qualityVersion, releaseGroup, sceneName, size, dateAdded, languages[], mediaInfo, sourcePath, recycleBinPath`.

## Radarr `Download` payload (WebhookImportPayload)

| Field | Type |
|---|---|
| `movie` | WebhookMovie |
| `remoteMovie` | WebhookRemoteMovie (ignore) |
| `movieFile` | WebhookMovieFile |
| `isUpgrade` | bool |
| `downloadClient` / `downloadClientType` / `downloadId` | string |
| `deletedFiles` | WebhookMovieFile[] |
| `customFormatInfo`, `release` | objects (ignore) |

**WebhookMovie**: `id, title, year, filePath, releaseDate, folderPath, tmdbId, imdbId, overview, genres[], images[], tags[] (label strings), originalLanguage`.

**WebhookMovieFile**: `id, relativePath, path, quality, qualityVersion, releaseGroup, sceneName, indexerFlags, size, dateAdded, languages[], mediaInfo, sourcePath, recycleBinPath`.

## Modeling notes for v2

1. **Fields v2 actually needs**: `eventType`, `isUpgrade`, `movieFile.path` / `episodeFile.path`, `movie.folderPath` / `series.path`, `movie.title/year` / `series.title` + `episodes[].seasonNumber/episodeNumber`, `movie.tags` / `series.tags` (preset mapping), `instanceName` (logging). Everything else: model as optional/ignored — use pydantic `extra="ignore"` so Arr version drift never breaks parsing.
2. **Media type detection**: presence of `movie` vs `series` keys — authoritative, no filename regex needed for webhook jobs.
3. **`tags` are label strings** on the series/movie object (only in newer Arr versions; default to empty list).
4. **Upgrades**: an upgrade replaces the source file — v2 must reprocess (fingerprint changes since source identity changed) and replace the previous clean output; `deletedFiles` tells us which old source went away.
5. All payload classes share the base fields, so a small discriminated-union parse on `eventType` + presence of `movie`/`series` is enough; unknown events fall through to "ignored".

Sources: [Sonarr webhook source](https://github.com/Sonarr/Sonarr/tree/develop/src/NzbDrone.Core/Notifications/Webhook), [Radarr webhook source](https://github.com/Radarr/Radarr/tree/develop/src/NzbDrone.Core/Notifications/Webhook)
