# Censorr packaged as a Python application.
#
# The single package can run every role (CLI `process`, `serve`, `work`) just
# like the single Docker image — `serve`/`work` deps (fastapi, uvicorn) are
# always included so one closure covers both systemd units.
{
  lib,
  buildPythonApplication,
  setuptools,
  # runtime deps (pyproject [project.dependencies] + [serve] extra)
  typer,
  pydantic,
  rapidfuzz,
  pysubs2,
  rich,
  fastapi,
  uvicorn,
  # test deps
  pytestCheckHook,
  httpx,
  # system dep: FFmpeg >= 6 on PATH (N1). ffmpeg-headless is enough — no GUI,
  # no X — and keeps the closure small.
  ffmpeg-headless,
  makeWrapper,
  # When true, also run the @pytest.mark.ffmpeg integration suite at build
  # time (slower; needs ffmpeg in the build sandbox). Off by default so the
  # package build stays fast; `nix flake check` exercises it separately.
  runIntegrationTests ? false,
}:

buildPythonApplication {
  pname = "censorr";
  version = "2.0.0";
  pyproject = true;

  # Only the sources that affect the build — keeps rebuilds from triggering on
  # unrelated edits (docs, .sop planning, CI).
  src = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [
      ../pyproject.toml
      ../README.md
      ../censorr
      ../tests
    ];
  };

  build-system = [ setuptools ];

  dependencies = [
    typer
    pydantic
    rapidfuzz
    pysubs2
    rich
    fastapi
    uvicorn
  ];

  nativeBuildInputs = [ makeWrapper ];

  # media/ and audio/qc.py shell out to ffmpeg/ffprobe on PATH (N1). Wrapping
  # the entry point guarantees they resolve regardless of the caller's
  # environment; the systemd units also put ffmpeg on PATH as belt-and-braces.
  makeWrapperArgs = [
    "--prefix"
    "PATH"
    ":"
    (lib.makeBinPath [ ffmpeg-headless ])
  ];

  nativeCheckInputs = [
    pytestCheckHook
    httpx
  ] ++ lib.optional runIntegrationTests ffmpeg-headless;

  # Unit + contract by default (pure logic, deterministic, no daemons). The
  # docker-marked tests need a Docker daemon, unavailable in the Nix sandbox;
  # the ffmpeg suite is opt-in via runIntegrationTests.
  disabledTestMarks = [ "docker" ] ++ lib.optional (!runIntegrationTests) "ffmpeg";

  pythonImportsCheck = [ "censorr" ];

  meta = {
    description = "Censors profane audio and subtitles in media files for Plex/Sonarr/Radarr";
    homepage = "https://github.com/jhaycr/censorr";
    license = lib.licenses.mit;
    mainProgram = "censorr";
    platforms = lib.platforms.linux;
  };
}
