{
  pkgs,
  overlayfsLib,
  modules,
}:
{
  # A fixed-output derivation containing the original Autodesk install image.
  media,
  updates ? [ ],
  version ? "2026",
  contentCenter ? true,
}:
let
  inherit (pkgs) lib;
  inventorMeta = {
    description = "Autodesk Inventor 2026 through Wine and nix-overlayfs";
    homepage = "https://www.autodesk.com/products/inventor/overview";
    license = lib.licenses.unfree;
    platforms = [ "x86_64-linux" ];
  };
  # The composed launcher and captured installation both contain Autodesk code.
  withInventorMeta =
    package: executable:
    package.overrideAttrs (old: {
      meta = (old.meta or { }) // inventorMeta // { mainProgram = executable; };
      passthru = (old.passthru or { }) // {
        basePackage = package.basePackage.overrideAttrs (base: {
          meta = (base.meta or { }) // inventorMeta;
        });
      };
    });
  # Licensing and SSO stay alive after Inventor exits. End this prefix's Wine
  # session when the main process exits so overlayfs can unmount it cleanly.
  launchWine = pkgs.writeShellScript "inventor-wine-session" ''
    set +e
    ${modules.runtime.toolsPackage}/bin/wine "$@"
    status=$?
    ${modules.runtime.toolsPackage}/bin/wineserver -k
    exit "$status"
  '';
  runtime = modules.runtime // {
    mkSession =
      args:
      let
        session = modules.runtime.mkSession args;
      in
      session
      // {
        commands =
          session.commands
          // lib.optionalAttrs (args.phase == "launch") {
            wine = "${launchWine}";
          };
      };
  };
  tools = [
    pkgs.python3
    pkgs._7zz
    pkgs.cabextract
    pkgs.unzip
    pkgs.coreutils
    pkgs.findutils
    pkgs.gnugrep
    pkgs.gnused
    pkgs.gawk
    pkgs.gnutar
    pkgs.xz
  ];
  fonts = pkgs.symlinkJoin {
    name = "inventor-fonts";
    paths = [
      pkgs.liberation_ttf
      pkgs.dejavu_fonts
      pkgs.noto-fonts
      pkgs.carlito
      pkgs.caladea
    ];
  };
  dxvkArchive = pkgs.fetchurl {
    url = "https://github.com/doitsujin/dxvk/releases/download/v2.7.1/dxvk-2.7.1.tar.gz";
    hash = "sha256-2Fznx59X7NdlqqG55wB8uHXm/en20zHfeZvOc9UTzoc=";
  };
  webview2 =
    (overlayfsLib.mkWindowsPackage {
      inherit (modules) runtime;
      pname = "inventor-webview2";
      version = "154.0.4258.62";
      packageName = "inventor-webview2";
      src = pkgs.fetchurl {
        url = "https://msedge.sf.dl.delivery.mp.microsoft.com/filestreamingservice/files/18c66e75-0385-4019-be3f-3f4a2bb867d5/MicrosoftEdgeWebView2RuntimeInstallerX64.exe";
        hash = "sha256-rCLs3BnFuIuH8/p1LADalUFlOo9cDF/Eo7K26+ZZH2k=";
        meta.license = lib.licenses.unfree;
      };
      unshareInstall = { session, ... }: ''
        set -euo pipefail
        ${session.commands.wine} "$src" /silent /install
        ${pkgs.coreutils}/bin/timeout 60 ${session.commands.wineserver} --wait || ${session.commands.wineserver} -k
        test -n "$(${pkgs.findutils}/bin/find "$WINEPREFIX/drive_c" -name msedgewebview2.exe -print -quit)"
      '';
    }).overrideAttrs
      (old: {
        meta = (old.meta or { }) // {
          license = lib.licenses.unfree;
        };
      });
in
withInventorMeta (overlayfsLib.mkWindowsPackage {
  inherit runtime;
  inherit version;
  portableReparsePoints = true;
  pname = "inventor";
  packageName = "autodesk-inventor-2026";
  executableName = "inventor";
  executablePath = "/drive_c/Program Files/Autodesk/Inventor 2026/Bin/Inventor.exe";
  workingDirectory = "/drive_c/Program Files/Autodesk/Inventor 2026/Bin";
  src = media;
  overlayDependencies = [ webview2 ];
  # These replace Wine's stock DLLs; keep them when the library prunes duplicates.
  extraPathsToInclude =
    lib.concatMap
      (
        directory:
        map (dll: "windows/${directory}/${dll}.dll") [
          "d3d8"
          "d3d9"
          "d3d10core"
          "d3d11"
          "dxgi"
        ]
      )
      [
        "system32"
        "syswow64"
      ];
  unshareInstall = { session, ... }: ''
    set -euo pipefail
    export PATH=${lib.makeBinPath tools}:${modules.runtime.toolsPackage}/bin:$PATH
    export INV_WINE=system INV_SANDBOX=0 INV_DATA_DIR="" INV_FONTS=linux
    export INV_NORMALIZE_REPARSE=${session.commands.normalizeReparsePoints}
    export INV_PREFIX="$WINEPREFIX" INV_LOGDIR="$TMPDIR/inventor-logs"
    export XDG_CACHE_HOME="$TMPDIR/inventor-cache"
    mkdir -p "$INV_LOGDIR" "$TMPDIR/inventor-project" "$TMPDIR/inventor-downloads"
    cp -R ${../scripts} "$TMPDIR/inventor-project/scripts"
    cp -R ${../wine} "$TMPDIR/inventor-project/wine"
    mkdir -p "$TMPDIR/inventor-project/registry"
    chmod -R u+w "$TMPDIR/inventor-project"
    cat > "$TMPDIR/inventor-project/config.env" <<'EOF'
    INV_FONT_DIRS=(${fonts}/share/fonts ${modules.runtime.toolsPackage}/share/wine)
    EOF
    export DOWNLOAD_DIR="$TMPDIR/inventor-downloads"
    ln -s ${dxvkArchive} "$DOWNLOAD_DIR/dxvk-2.7.1.tar.gz"
    python3 "$TMPDIR/inventor-project/scripts/install-from-image.py" "$src" \
      --prefix "$WINEPREFIX" --prepared-prefix --preinstalled-webview2 ${
        lib.optionalString (!contentCenter) "--no-content"
      }
    ${lib.concatMapStringsSep "\n" (update: ''
      python3 "$TMPDIR/inventor-project/scripts/install-from-image.py" ${lib.escapeShellArg (toString update)} \
        --prefix "$WINEPREFIX"
    '') updates}
    ${session.commands.normalizeReparsePoints} "$WINEPREFIX"
    bash "$TMPDIR/inventor-project/scripts/finish-install.sh" --no-sandbox
    ${session.commands.wineserver} --wait
    test -s "$WINEPREFIX/drive_c/windows/Fonts/NotoSans.ttf"
    test -s "$WINEPREFIX/drive_c/windows/Fonts/LiberationSans-Regular.ttf"
    test -s "$WINEPREFIX/drive_c/windows/Fonts/DejaVuSans.ttf"
    test -f "$WINEPREFIX/drive_c/Program Files/Autodesk/Inventor 2026/Bin/Inventor.exe"
  '';
  runtimeEnvVars = {
    WINE_LARGE_ADDRESS_AWARE = "1";
    WINEDLLOVERRIDES = "msquic=;winemenubuilder.exe=d";
  };
  urlSchemes = [ "adskidmgr" ];
  entrypointWrapper = entrypoint: ''
    case "''${1:-}" in
      adskidmgr:*) exec ${entrypoint} --nix-overlayfs-open-url "$1" ;;
      *) exec ${entrypoint} "$@" ;;
    esac
  '';
  urlSchemeOpenCommands = ''
    exec ${modules.runtime.toolsPackage}/bin/wine \
      'C:\Program Files\Autodesk\AdskIdentityManager\Current\AdskIdentityManager.exe' "$callback_url"
  '';
  extraPreLaunchCommands = ''
    export PATH=${modules.runtime.toolsPackage}/bin:${
      lib.makeBinPath (tools ++ [ pkgs.util-linux ])
    }:$PATH
    ${builtins.readFile ./launch-lock.sh}
    ${(overlayfsLib.mkGraphicsBootstrap {
      inherit (modules) runtime;
      defaultMode = "system";
    }).extraPreLaunchCommands
    }
    ${builtins.readFile ./launch-services.sh}
  '';
}) "inventor"
