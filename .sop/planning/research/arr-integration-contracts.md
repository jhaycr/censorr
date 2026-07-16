# Research: Sonarr/Radarr Integration Contracts (External Validation)

What Sonarr and Radarr actually send, so v2's service API can accept native payloads. Gathered 2026-07-15.

## Webhook (Settings → Connect → Webhook)

Arr apps POST JSON to a configured URL on selected events. Relevant event: `Download` (fires on import and upgrade; `isUpgrade` distinguishes).

**Radarr** (`eventType: "Download"`), key fields:
```json
{
  "eventType": "Download",
  "movie": {"id": 1, "title": "...", "year": 2024, "folderPath": "/data/media/movies/Movie (2024)", "tags": ["..."]},
  "movieFile": {"path": "/data/media/movies/Movie (2024)/Movie (2024).mkv", "relativePath": "...", "quality": "...", "size": 123},
  "isUpgrade": false,
  "applicationUrl": "", "instanceName": "Radarr"
}
```

**Sonarr** (`eventType: "Download"`), key fields:
```json
{
  "eventType": "Download",
  "series": {"id": 1, "title": "...", "path": "/data/media/tv/Show", "tvdbId": 123, "tags": ["..."]},
  "episodes": [{"id": 1, "episodeNumber": 1, "seasonNumber": 1, "title": "..."}],
  "episodeFile": {"path": "/data/media/tv/Show/Season 01/Show - s01e01.mkv", "relativePath": "...", "quality": "..."},
  "isUpgrade": false, "instanceName": "Sonarr"
}
```

Notes:
- `tags` on movie/series are **label strings** (and only included in newer versions) — not a dict. v1's expected `tags: {censorr_preset: ...}` shape cannot be produced by a native Arr webhook.
- Both send `eventType: "Test"` when the user clicks Test — the endpoint must return success for it without processing.
- Media type is unambiguous from the payload shape (`movie`/`movieFile` vs `series`/`episodeFile`) — no filename guessing needed.

Sources: [Radarr webhook payload example (handbrake-webhook)](https://github.com/chrisjohnson00/handbrake-webhook), [Radarr issue #10029 — webhook payload fields](https://github.com/Radarr/Radarr/issues/10029), [Radarr API docs](https://radarr.video/docs/api/)

## Custom Script (Settings → Connect → Custom Script)

Passes data via **environment variables**, not args/JSON:
- Sonarr: `sonarr_eventtype`, `sonarr_episodefile_path`, `sonarr_series_path`, `sonarr_series_title`, season/episode numbers, etc.
- Radarr: `radarr_eventtype`, `radarr_moviefile_path`, `radarr_movie_path`, `radarr_movie_title`, `radarr_movie_year`, etc.
- Event `Test` sends `*_eventtype=Test`.

The README's current example (`Arguments: ... "{{file_path}}"`) is not a real Arr mechanism — custom scripts receive no templated arguments. A correct v2 custom-script shim reads the env vars and either calls the CLI directly or POSTs to the service.

Sources: [Servarr wiki: Sonarr custom scripts](https://wiki.servarr.com/sonarr/custom-scripts), [Sonarr wiki: Custom Post Processing Scripts](https://github.com/Sonarr/Sonarr/wiki/Custom-Post-Processing-Scripts)

## Path mapping

Arr and Censorr may see different mount points for the same files (e.g. Arr's `/data/media/movies` vs host `/mnt/media/movies`). v2 needs an explicit, configurable path-mapping table (`arr_prefix → local_prefix`), applied to every incoming path, with a clear error when an incoming path matches no mapping and doesn't exist locally.

## Preset selection options for v2 (decision needed)

1. **Per-endpoint**: `/webhook/radarr` → preset from query (`?preset=movies`) or per-source default in config. Simple, explicit; recommended.
2. **Arr tag mapping**: config maps Arr label tags (e.g. tag `censorr-strict` on a series) → preset. Enables per-show/per-movie policies from inside Arr; requires tags present in payload (newer Arr versions).
3. **Media-type default**: payload shape alone picks `movies`/`tv` preset when nothing else specified — the minimal-input default.

These compose: explicit query > tag mapping > media-type default.
