# This table says where the Nix package has each prefix migration of the
# script installer (scripts/lib/migrations/). The Nix build does not run
# them: an installation layer is built in one go, so there is no older prefix
# to bring up to date. The flake check `migration-parity` warns when a
# migration file has no entry here (it does not fail, because migrations come
# from the script installer's side), so that a new migration gets a decision
# for the Nix package too. The kinds are:
#   post-install   nix/post-install.sh, in the installation layer (needs the
#                  installed files; a change reinstalls Inventor)
#   config-layer   nix/config-layer.sh, a separate layer from the installation
#                  (a change rebuilds that layer and the launcher only)
#   installer      install-from-image.py already does it for a new installation
#   launcher       the launcher or nix-overlayfs does it at runtime
#   layers         a Nix layer (DXVK, vkd3d-proton, .NET, WebView2)
#   not-applicable nothing to do in a Nix build
{
  "0001-base-setup" = {
    nix = [
      "post-install"
      "config-layer"
      "installer"
      "launcher"
      "layers"
      "not-applicable"
    ];
    note = ''
      post-install: Current links, Shared Components and Path registry,
      licensing service on manual start, SSO plugin, default add-ins off,
      crash sources, WPF stubs, RealDWG settings, the M: drive.
      Windows 10 mode (install-from-image.py sets it too); values read back.
      config-layer: fonts (linux-fonts.sh), WebView2 registry (webview2_reg).
      launcher: X11/Wayland driver
      (launch-services.sh), adskidmgr handler (urlSchemes).
      layers: DXVK, vkd3d-proton. not-applicable: isolation (no sandbox).
    '';
  };
  "0002-winum-runtime" = {
    nix = [ "not-applicable" ];
    note = "Layers are built with one Wine; a launch Wine that changes the prefix is refused (nix/wine-prefix.nix).";
  };
  "0003-x11-driver-inventor" = {
    nix = [ "config-layer" ];
    note = "UseEGL=N, ClientSideWithRender=N for Inventor.exe.";
  };
  "0004-enable-hydra" = {
    nix = [ "not-applicable" ];
    note = "Optional, run only by name; not in the Nix package.";
  };
  "0005-inventor-registration" = {
    nix = [ "installer" ];
    note = "install-from-image.py runs Inventor.exe /install 0.";
  };
  "0006-bsdtar-tar-exe" = {
    nix = [ "installer" ];
    note = "install-from-image.py puts tar.exe in place (bsdtar archive linked into DOWNLOAD_DIR).";
  };
  "0007-public-documents-paths" = {
    nix = [
      "installer"
      "post-install"
    ];
    note = "install-from-image.py maps [{Common Documents}] since 2026-11-16; post-install fixes any %PUBLIC% left in plain values, both registry views.";
  };
  "0008-public-documents-paths-wow64" = {
    nix = [
      "installer"
      "post-install"
    ];
    note = "As 0007, 32-bit registry view (post-install covers both views).";
  };
  "0009-vkd3d-proton-winum" = {
    nix = [ "layers" ];
    note = "winum's vkd3d-proton is a layer in nix/inventor.nix.";
  };
  "0010-default-addins-on" = {
    nix = [ "not-applicable" ];
    note = "A new installation never had these add-ins off; post-install turns off only the Assistant.";
  };
  "0012-tutorial-off-without-dotnet48" = {
    nix = [ "not-applicable" ];
    note = "Turns the Interactive Tutorial off only without .NET Framework 4.8; the Nix package always has the dotnet-framework-4-8 layer, so it stays on (post-install.sh turns off only the Assistant).";
  };
  "0011-winemenubuilder-off" = {
    nix = [
      "config-layer"
      "launcher"
    ];
    note = "DllOverrides winemenubuilder.exe = \"\" in the prefix (config layer) and in the launcher's dllOverrides; the build has no host menus to remove.";
  };
}
