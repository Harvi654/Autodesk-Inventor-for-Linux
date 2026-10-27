{ self }:
{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.programs.autodesk-inventor;
  icons = pkgs.runCommand "autodesk-inventor-icons" { } ''
    for size in 16 24 32 48 64 128 256; do
      install -Dm644 ${../config/icons}/hicolor/''${size}x''${size}/inventor-on-linux.png \
        "$out/share/icons/hicolor/''${size}x''${size}/apps/inventor-on-linux.png"
    done
    install -Dm644 ${../config/icons/inventor-on-linux.svg} \
      "$out/share/icons/hicolor/scalable/apps/inventor-on-linux.svg"
  '';
  defaultPackages = {
    "2026" = self.packages.x86_64-linux.inventor-2026;
    "2027" = self.packages.x86_64-linux.inventor-2027;
  };
  packageFor =
    year: if year == "2026" then cfg.package else cfg.packages.${year} or defaultPackages.${year};
  desktopNameFor = year: if year == "2026" then "autodesk-inventor" else "autodesk-inventor-${year}";
  desktopFor =
    year:
    pkgs.makeDesktopItem {
      name = desktopNameFor year;
      desktopName = "Autodesk Inventor ${year}";
      icon = "inventor-on-linux";
      exec = "${lib.getExe (packageFor year)} %U";
      terminal = false;
      categories = [
        "Graphics"
        "Engineering"
      ];
      mimeTypes = [ "x-scheme-handler/adskidmgr" ];
    };
  newestYear =
    if cfg.versions == [ ] then "2026" else lib.last (lib.sort builtins.lessThan cfg.versions);

in
{
  options.programs.autodesk-inventor = {
    enable = lib.mkEnableOption "Autodesk Inventor through Wine and nix-overlayfs";
    versions = lib.mkOption {
      type = lib.types.listOf (
        lib.types.enum [
          "2026"
          "2027"
        ]
      );
      default = [ "2026" ];
      description = "Inventor releases to install, each with separate persistent state.";
    };
    packages = lib.mkOption {
      type = lib.types.attrsOf lib.types.package;
      default = { };
      description = "Packages by release, optionally overridden with lib.mkInventor.";
    };
    package = lib.mkOption {
      type = lib.types.package;
      default = cfg.packages."2026" or defaultPackages."2026";
      description = "Inventor 2026 package; retained for compatibility with existing configurations.";
    };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = cfg.versions != [ ] && lib.unique cfg.versions == cfg.versions;
        message = "programs.autodesk-inventor.versions must contain at least one release, without duplicates.";
      }
      {
        assertion = pkgs.stdenv.hostPlatform.system == "x86_64-linux";
        message = "Autodesk Inventor currently supports x86_64-linux only.";
      }
    ];
    environment.systemPackages = [
      icons
    ]
    ++ lib.concatMap (year: [
      (packageFor year)
      (desktopFor year)
    ]) cfg.versions;
    hardware.graphics.enable = true;
    programs.fuse.enable = true;
    xdg.mime.enable = true;
    xdg.mime.defaultApplications."x-scheme-handler/adskidmgr" = "${desktopNameFor newestYear}.desktop";
  };
}
