# Censorr

Censorr takes a movie or TV episode, finds profanity via its subtitles, and produces a
**new, clean copy** — profane audio muted, subtitles masked — named and placed so Plex
resolves it correctly. The original file is never touched.

- **Correct censoring first**: every mute window covers the whole subtitle entry plus a
  buffer on both sides, and the output is verified (under- *and* over-censoring checks)
  before it's published. A file that fails QC never reaches your library.
- **Plex-correct outputs**: movies become `Title (Year) {edition-Censorr}.mkv`, episodes
  keep their filename — both under separate `*-clean` roots you point a separate,
  access-controlled Plex library at.
- **Arr-native**: Sonarr/Radarr call Censorr's webhooks directly on import. Only items
  you've tagged (default tag: `censorr`) are processed.

## Quick start (Docker Compose)

```bash
cp .env.example .env        # set MEDIA_PATH_* to your library paths
docker compose up -d --build
curl http://localhost:8000/healthz
```

Two services run from one image: `serve` (webhook/API — mounts no media) and `work`
(the pipeline worker — mounts sources read-only, clean roots read-write). Jobs flow
through a crash-safe file queue on a shared volume; nothing else is required.

Edit `config/censorr.toml` (mounted into both containers) to adjust behavior; the
defaults work for the compose-defined mount layout.

### Connecting Radarr / Sonarr

In each Arr instance, add a **Webhook** connection (Settings → Connect → + → Webhook):

| Setting | Value |
|---|---|
| URL | `http://<censorr-host>:8000/webhook/radarr` (or `/webhook/sonarr`) |
| Method | POST |
| Notification triggers | **On File Import** and **On File Upgrade** |

Click **Test** — Censorr answers it. Then add the `censorr` tag to any movie/series you
want censored versions of; untagged items are ignored. (Set `require_tags = []` in
`censorr.toml` to censor everything instead.)

Optional extras:
- **Shared secret**: set `[service] secret` in censorr.toml, then append `?token=<secret>`
  to the webhook URL.
- **Preset per tag**: map Arr tags to config presets via `[arr_tag_presets]`, or force one
  with `?preset=<name>` on the URL.
- **Upgrades**: handled automatically — the new import is processed and the superseded
  clean copy is deleted.

## CLI

```bash
censorr process <file>            # censor one file (skips if already up to date; --force)
censorr process <file> --dry-run  # show tracks, matches, mute windows, planned names
censorr inspect <file>            # same analysis, presentation-focused
censorr reprocess <root>          # bulk: walk a library, (re)process stale files only
censorr reconcile <clean_root>    # delete clean copies whose source is gone (--dry-run)
censorr gc                        # sweep expired failed workdirs + job records
censorr serve / censorr work      # the two service roles
```

Zero-config contract: a bare `censorr process movie.mkv` works — bundled word list,
English subtitles, derived clean root (`<library-root>-clean`). Configuration only
customizes.

Exit codes: `0` published · `2` skipped (already clean, no text subtitles, …) ·
`3` invalid input/config · `4` failed quality verification · `1` transient error.

## How it decides what to mute

Detection runs on the file's **text subtitles** (embedded, or a sidecar `.srt` next to
the source): fuzzy matching against a word list catches inflections, compounds, and
misspellings (`fucking`, `motherfucker`, `unfuckingbelievable`) while a length-based
threshold floor and an allowlist suppress false positives (`shirt`, `duck`, `damage`).
Every matched entry's full time span — plus `buffer_s` (default 0.2 s) on each side — is
muted in the audio, and the matched words are masked (`f***`) in the embedded subtitle
track. A second embedded "mute captions" track carries only the masked lines, flagged
forced+default, so players show the masked text during muted spans automatically.

Degraded cases are explicit, never silent: no text subtitles → skipped (visible reason);
audio language ≠ subtitle language (e.g. anime) → subtitles-only mode (masked subs,
audio untouched); zero matches → episodes still get a stream-copied clean copy so the
clean library stays complete, movies skip by default (`[behavior]`).

## Configuration reference

Everything is optional; this shows the defaults.

```toml
[detect]
# wordlist = "wordlist.json"          # override/extend the bundled list
buffer_s = 0.2                        # mute buffer on each side of a matched entry
fuzzy_threshold = 85

[subtitles]
language = "en"
exclude_titles = ["sdh", "hi", "cc"]
mute_captions = true                  # forced+default track shown during mutes
allow_language_mismatch = true        # false -> skip instead of subtitles-only mode

[audio]
fallback_codec = "eac3"               # when the source codec can't be re-encoded
fallback_bitrate = "640k"

[naming]
edition_tag = "Censorr"
write_sidecar = false                 # embedded subtitles are the primary delivery
sidecar_token = "censorr"             # sidecar naming token when enabled; "" = pure Plex
# movie_clean_root = "/data/media/movies-clean"   # unset -> derived <root>-clean
# tv_clean_root = "/data/media/tv-clean"          # unset -> derived <root>-clean

[behavior]
on_clean_tv = "publish"               # zero-match episode: publish stream-copy | skip
on_clean_movie = "skip"
fail_on_no_subtitles = false

[qc]
audio_min_drop_db = -12.0             # muted windows must drop this far below control
max_mute_ratio = 0.05                 # fail if > 5% of runtime is muted
max_window_s = 15.0
warn_matched_entry_ratio = 0.20
warn_masked_entry_ratio = 0.15
continue_on_audio_qc_fail = false
continue_on_subtitle_qc_fail = false

[service]
secret = ""                           # webhook shared secret (?token= or X-Webhook-Secret)
queue_path = "/app/queue"
max_retries = 3
lease_seconds = 1800
failed_ttl_days = 7
record_ttl_days = 30
require_tags = ["censorr"]            # Arr tag gate; [] processes everything
[service.path_map]                    # Arr's path view -> worker's path view
"/data/media" = "/data/media"

[presets.movies]                      # any table above can be overridden per preset
[presets.tv]
[arr_tag_presets]
# censorr-strict = "strict"           # Arr tag -> preset name

# Custom word list format (detect.wordlist):
# {"words": [{"word": "...", "threshold": 90, "replacement": "...", "aggressive": true}],
#  "allowlist": ["never-censor-this"]}
```

The word list merges over the bundled default (same-word entries override it; the
allowlist extends it).

## Development

```bash
pip install -e .[dev,serve]
pytest                       # unit + contract + integration (needs ffmpeg on PATH)
pytest -m "not ffmpeg"       # fast, pure-logic tests only
pytest -m docker             # container smoke tests (needs docker)
ruff check . && mypy censorr
```

See `CLAUDE.md` for the architecture map.
