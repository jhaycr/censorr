# NixOS module: deploy Censorr as the same two roles the Docker Compose stack
# runs — `serve` (webhooks + jobs API + web UI) and `work` (pipeline worker) —
# as systemd units sharing a file queue on local state.
#
# Enable with `services.censorr.enable = true` after importing this module
# (the flake exposes it as `nixosModules.default`). Set the clean roots the
# worker publishes into and point Radarr/Sonarr webhooks at the serve port.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.services.censorr;
  tomlFormat = pkgs.formats.toml { };
  configFile = tomlFormat.generate "censorr.toml" cfg.settings;

  # Clean roots the worker writes into — collected from settings so the
  # sandbox grants exactly the media paths that need write access.
  cleanRoots = lib.filter (p: p != null) [
    (cfg.settings.naming.movie_clean_root or null)
    (cfg.settings.naming.tv_clean_root or null)
  ];

  # Hardening shared by both units. The serve role never writes media; the
  # worker adds the clean roots to ReadWritePaths below.
  commonHardening = {
    DynamicUser = false;
    User = cfg.user;
    Group = cfg.group;
    StateDirectory = "censorr";
    WorkingDirectory = "/var/lib/censorr";
    Restart = "on-failure";
    RestartSec = 5;
    NoNewPrivileges = true;
    ProtectSystem = "strict";
    ProtectHome = true;
    PrivateTmp = true;
    ProtectKernelTunables = true;
    ProtectKernelModules = true;
    ProtectControlGroups = true;
    RestrictSUIDSGID = true;
    RestrictRealtime = true;
    LockPersonality = true;
  };
in
{
  options.services.censorr = {
    enable = lib.mkEnableOption "Censorr media profanity censor (serve + work)";

    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.callPackage ./censorr.nix { };
      defaultText = lib.literalExpression "pkgs.callPackage ./censorr.nix { }";
      description = "The censorr package to run.";
    };

    user = lib.mkOption {
      type = lib.types.str;
      default = "censorr";
      description = ''
        User the services run as. Must be able to read your media sources and
        write the configured clean roots. If left as the default the module
        creates it as a system user.
      '';
    };

    group = lib.mkOption {
      type = lib.types.str;
      default = "censorr";
      description = "Primary group for the service user (created if it is the default).";
    };

    settings = lib.mkOption {
      type = tomlFormat.type;
      default = { };
      example = lib.literalExpression ''
        {
          naming = {
            movie_clean_root = "/srv/media/movies-clean";
            tv_clean_root = "/srv/media/tv-clean";
          };
          service = {
            secret = "change-me";
            path_map = { "/srv/media" = "/srv/media"; };
          };
        }
      '';
      description = ''
        Contents of `censorr.toml`, rendered to a read-only file in the Nix
        store and passed to every role with `--config`. See the README for the
        full schema. `service.queue_path` defaults to the shared state
        directory. Because the file lives in the store, the web UI's config
        editor is read-only under NixOS — manage config here declaratively.
      '';
    };

    serve = {
      enable = lib.mkOption {
        type = lib.types.bool;
        default = true;
        description = "Run the webhook/API/UI service.";
      };
      host = lib.mkOption {
        type = lib.types.str;
        default = "0.0.0.0";
        description = "Address the API binds to.";
      };
      port = lib.mkOption {
        type = lib.types.port;
        default = 8000;
        description = "Port the API listens on.";
      };
      openFirewall = lib.mkOption {
        type = lib.types.bool;
        default = false;
        description = "Open the serve port in the firewall.";
      };
    };

    worker = {
      enable = lib.mkOption {
        type = lib.types.bool;
        default = true;
        description = "Run the pipeline worker.";
      };
      extraArgs = lib.mkOption {
        type = lib.types.listOf lib.types.str;
        default = [ ];
        example = [ "--poll-interval" "10" ];
        description = "Extra arguments appended to `censorr work`.";
      };
    };
  };

  config = lib.mkIf cfg.enable {
    # Default the queue onto the shared state dir unless the operator overrides
    # it. mkDefault so an explicit settings.service.queue_path still wins.
    services.censorr.settings.service.queue_path =
      lib.mkDefault "/var/lib/censorr/queue";

    assertions = [
      {
        assertion = cfg.worker.enable -> cleanRoots != [ ];
        message =
          "services.censorr.worker is enabled but no clean root is set; "
          + "set services.censorr.settings.naming.movie_clean_root and/or "
          + "tv_clean_root (the worker refuses to start without a writable root, N7).";
      }
    ];

    users.users = lib.mkIf (cfg.user == "censorr") {
      censorr = {
        isSystemUser = true;
        group = cfg.group;
        description = "Censorr service user";
      };
    };
    users.groups = lib.mkIf (cfg.group == "censorr") { censorr = { }; };

    networking.firewall.allowedTCPPorts =
      lib.mkIf (cfg.serve.enable && cfg.serve.openFirewall) [ cfg.serve.port ];

    systemd.services.censorr-serve = lib.mkIf cfg.serve.enable {
      description = "Censorr serve (webhooks + jobs API + web UI)";
      wantedBy = [ "multi-user.target" ];
      after = [ "network.target" ];
      serviceConfig = commonHardening // {
        ExecStart = lib.escapeShellArgs [
          (lib.getExe cfg.package)
          "serve"
          "--config"
          "${configFile}"
          "--host"
          cfg.serve.host
          "--port"
          (toString cfg.serve.port)
        ];
      };
    };

    systemd.services.censorr-work = lib.mkIf cfg.worker.enable {
      description = "Censorr work (pipeline worker)";
      wantedBy = [ "multi-user.target" ];
      after = [ "network.target" ] ++ lib.optional cfg.serve.enable "censorr-serve.service";
      # ffmpeg is already wrapped onto the package's PATH; add it to the unit
      # PATH too so any subprocess resolves it identically.
      path = [ pkgs.ffmpeg-headless ];
      serviceConfig = commonHardening // {
        ReadWritePaths = cleanRoots;
        ExecStart = lib.escapeShellArgs (
          [
            (lib.getExe cfg.package)
            "work"
            "--config"
            "${configFile}"
          ]
          ++ cfg.worker.extraArgs
        );
      };
    };
  };

  meta.maintainers = [ ];
}
