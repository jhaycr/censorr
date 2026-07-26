# Censorr

Censorr takes a movie or TV episode, finds profanity via its subtitles, and produces a
**new, clean copy** — profane audio muted, subtitles masked — named and placed so Plex
resolves it correctly. The original file is never touched.

> **Personal project, no support.** Built largely with AI code-generation tools
> to scratch my own itch. Shared in case it's useful to you too. Issues and
> feature requests are welcome and I read them all, but responses and fixes
> happen on hobby-project time. Review and test before relying on it.

## 🤖 An AI-native project

Censorr is built AI-natively: the requirements interrogation, research, adversarial
design review, 15-step implementation plan, code, tests, and this README were produced
by Claude (Anthropic) working in Claude Code, directed and reviewed by a human
maintainer who owns every product decision. The full paper trail ships in the repo:
`.sop/planning/` holds the idea-honing Q&A (19 recorded decisions), the detailed design
(requirements R1–R16/N1–N7 referenced throughout the code), the research notes, and the
step-by-step implementation plan the commits follow. Read the git history alongside
those documents and you can trace every behavior back to an explicit, human-approved
decision. Issues and PRs are welcome — expect AI to be a first-class participant in
triaging and addressing them.

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

Two services run from one image: `serve` (webhook/API + web UI — sources mounted
read-only for the path browser, never written) and `work` (the pipeline worker —
sources read-only, clean roots read-write). Jobs flow
through a crash-safe file queue on a shared volume; nothing else is required.

Edit `config/censorr.toml` (mounted into both containers) to adjust behavior; the
defaults work for the compose-defined mount layout.

## Deploy on NixOS (flake)

The flake ships a `censorr` package (FFmpeg wrapped onto its `PATH`) and a NixOS
module that runs the same two roles as systemd units — `censorr-serve` and
`censorr-work` — sharing a file queue under `/var/lib/censorr`.

```nix
# flake.nix
{
  inputs.censorr.url = "github:jhaycr/censorr";

  outputs = { nixpkgs, censorr, ... }: {
    nixosConfigurations.mediabox = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        censorr.nixosModules.default
        {
          services.censorr = {
            enable = true;
            serve.openFirewall = true;
            settings = {
              naming.movie_clean_root = "/srv/media/movies-clean";
              naming.tv_clean_root = "/srv/media/tv-clean";
              service.path_map = { "/srv/media" = "/srv/media"; };
              # service.secret = "…";  # then append ?token=… to webhook URLs
            };
          };
        }
      ];
    };
  };
}
```

`settings` is rendered to `censorr.toml` and passed to both roles (see the
[configuration reference](#configuration-reference) for the full schema). The
clean roots you set become the worker's only writable media paths; give the
`censorr` user read access to your sources. Config is file-managed only (the
service exposes no HTTP read/write access to it), so managing it declaratively
here is the natural fit. Point Radarr/Sonarr at the serve port exactly as below.

Ad-hoc use without the module: `nix run github:jhaycr/censorr -- process movie.mkv --dry-run`.

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

## Web UI

`serve` also hosts a single-page UI at `http://<censorr-host>:8000/` — no build chain,
no extra dependencies, talks only to the service's own API. Three things, one page:

- **Submit a job**: type or **Browse…** to a file or folder (the path browser walks the
  read-only source mounts, Q19), pick a preset, optionally **force**, and queue it. A
  folder queues a *backfill* — every source file beneath it (a season, show, or whole
  library) expands into individual jobs, skipping ones whose clean copy is already up to
  date unless you force.
- **History**: live job table (source, status, result, mode, censored count, progress,
  finished), filterable by status, refreshable — backed by the `/jobs` endpoints.
- **Configuration**: edit `censorr.toml` in the browser and save. Changes apply to
  webhooks immediately and to each subsequent job.

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

## Roadmap

The pipeline was designed with explicit seams for these (see
`.sop/planning/design/detailed-design.md`, R15), in rough priority order:

- **Subtitle downloading** (`subliminal`, behind a `censorr[subs]` extra): today a file
  with no embedded/sidecar *text* subtitles is skipped with a visible reason —
  bitmap-only (PGS/VOBSUB) releases included. A downloader step in the
  subtitle-acquisition chain makes those files processable. First planned addition.
- **Word-level mute precision** (`censorr[align]`, forced alignment of the known
  subtitle text): narrows each mute window toward the profane word instead of muting
  the whole line. Windows always keep the safety buffer on both sides — precision may
  shrink over-muting, never risk under-muting. Ships as a separate glibc-based image
  (its ML dependencies don't fit the Alpine base).
- **EDL / PlexAutoSkip export**: emit the computed mute windows as sidecar edit
  decision lists, so players that support them can skip/mute without a remuxed copy.
- **Additional language support**: selection and naming are language-parameterized
  already; a bundled non-English word list and localized track titles would complete it.

## Development

```bash
pip install -e .[dev,serve]
pytest                       # unit + contract + integration (needs ffmpeg on PATH)
pytest -m "not ffmpeg"       # fast, pure-logic tests only
pytest -m docker             # container smoke tests (needs docker)
ruff check . && mypy censorr
```

With Nix: `nix develop` drops you into a shell with the deps, FFmpeg, ruff, and
mypy on `PATH`; `nix flake check` builds the package and runs the unit, contract,
and FFmpeg-integration suites in the sandbox.

See `CLAUDE.md` for the architecture map.
