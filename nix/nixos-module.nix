{ self }:
{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.programs.autodesk-inventor;
  desktop = pkgs.makeDesktopItem {
    name = "autodesk-inventor";
    desktopName = "Autodesk Inventor 2026";
    exec = "${cfg.package}/bin/inventor %U";
    terminal = false;
    categories = [
      "Graphics"
      "Engineering"
    ];
    mimeTypes = [ "x-scheme-handler/adskidmgr" ];
  };
in
{
  options.programs.autodesk-inventor = {
    enable = lib.mkEnableOption "Autodesk Inventor 2026 through Wine and nix-overlayfs";
    package = lib.mkOption {
      type = lib.types.package;
      default = self.packages.x86_64-linux.inventor;
      description = "Inventor package, optionally overridden with lib.mkInventor.";
    };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = pkgs.stdenv.hostPlatform.system == "x86_64-linux";
        message = "Autodesk Inventor currently supports x86_64-linux only.";
      }
    ];
    environment.systemPackages = [
      cfg.package
      desktop
    ];
    hardware.graphics.enable = true;
    programs.fuse.enable = true;
    xdg.mime.enable = true;
    xdg.mime.defaultApplications."x-scheme-handler/adskidmgr" = "autodesk-inventor.desktop";
  };
}
