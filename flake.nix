{
  description = "Censorr — censors profane audio and subtitles in media files for Plex/Sonarr/Radarr";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    let
      # System-independent: an overlay adding `censorr` to a package set, and
      # the NixOS module that deploys the serve + work roles.
      overlay = final: prev: {
        censorr = final.python3Packages.callPackage ./nix/censorr.nix { };
      };
    in
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        censorr = pkgs.python3Packages.callPackage ./nix/censorr.nix { };
      in
      {
        packages = {
          default = censorr;
          censorr = censorr;
        };

        # `nix run . -- serve` / `nix run . -- work` mirror the container roles.
        apps.default = flake-utils.lib.mkApp { drv = censorr; };

        devShells.default = pkgs.mkShell {
          inputsFrom = [ censorr ];
          packages = [
            pkgs.ffmpeg-headless
            pkgs.ruff
            pkgs.mypy
            pkgs.python3Packages.pytest
            pkgs.python3Packages.pytest-cov
            pkgs.python3Packages.httpx
          ];
        };

        checks = {
          # Package build (runs unit + contract tests).
          censorr = censorr;
          # Integration suite over real FFmpeg-synthesized fixtures.
          integration = censorr.override { runIntegrationTests = true; };
        };
      }
    )
    // {
      overlays.default = overlay;
      nixosModules.default = ./nix/module.nix;
    };
}
