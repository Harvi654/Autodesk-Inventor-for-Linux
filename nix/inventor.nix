{
  pkgs,
  overlayfsLib,
  modules,
  wine,
}:
{
  # A fixed-output derivation containing the original Autodesk install image.
  media,
  updates ? [ ],
  year ? "2026",
  version ? year,
  executableName ? if year == "2026" then "inventor" else "inventor-${year}",
  contentCenter ? true,
  gpuRayTracing ? false,
}:
let
  inherit (pkgs) lib;
  inventorMeta = {
    description = "Autodesk Inventor ${year} through Wine and nix-overlayfs";
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
  launchWine =
    selectedRuntime:
    pkgs.writeShellScript "inventor-wine-session" ''
      set +e
      ${selectedRuntime.toolsPackage}/bin/wine "$@"
      status=$?
      ${selectedRuntime.toolsPackage}/bin/wineserver -k
      exit "$status"
    '';
  launchRuntime =
    selectedRuntime:
    selectedRuntime
    // {
      mkSession =
        args:
        let
          session = selectedRuntime.mkSession args;
        in
        session
        // {
          commands =
            session.commands
            // lib.optionalAttrs (args.phase == "launch") {
              wine = "${launchWine selectedRuntime}";
            };
        };
    };
  runtime = launchRuntime modules.runtime;
  preLaunch = selectedRuntime: ''
    export PATH=${selectedRuntime.toolsPackage}/bin:${
      lib.makeBinPath (tools ++ [ pkgs.util-linux ])
    }:$PATH
    ${builtins.readFile ./launch-lock.sh}
    ${(overlayfsLib.mkGraphicsBootstrap {
      runtime = selectedRuntime;
      defaultMode = "system";
    }).extraPreLaunchCommands
    }
    ${builtins.readFile ./launch-services.sh}
  '';
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
    pkgs.zstd
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
  vkd3dArchive = pkgs.fetchurl {
    url = "https://github.com/HansKristian-Work/vkd3d-proton/releases/download/v3.0.1/vkd3d-proton-3.0.1.tar.zst";
    sha256 = "3cf2315522af5e43605ef6d3c41dad91387040bf97199934f3f7ab76caaa2f0c";
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
  packageArgs = {
    inherit runtime;
    inherit version;
    portableReparsePoints = true;
    pname = "inventor";
    packageName = "autodesk-inventor-${year}";
    inherit executableName;
    executablePath = "/drive_c/Program Files/Autodesk/Inventor ${year}/Bin/Inventor.exe";
    workingDirectory = "/drive_c/Program Files/Autodesk/Inventor ${year}/Bin";
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
            "d3d12"
            "d3d12core"
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
      export INV_YEAR=${lib.escapeShellArg year}
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
      ln -s ${vkd3dArchive} "$DOWNLOAD_DIR/vkd3d-proton-3.0.1.tar.zst"
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
      test -f "$WINEPREFIX/drive_c/Program Files/Autodesk/Inventor ${year}/Bin/Inventor.exe"
    '';
    runtimeEnvVars = {
      INVENTOR_YEAR = year;
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
    extraPreLaunchCommands = preLaunch modules.runtime;
  };
  application = withInventorMeta (overlayfsLib.mkWindowsPackage packageArgs) executableName;
  rtExecutableName = "${executableName}-rt";
  gpu = import ./gpu-ray-tracing.nix {
    inherit
      pkgs
      overlayfsLib
      modules
      wine
      ;
  };
in
if gpuRayTracing then
  withInventorMeta (overlayfsLib.composeWindowsLayers {
    inherit (packageArgs)
      packageName
      executablePath
      workingDirectory
      runtimeEnvVars
      urlSchemes
      entrypointWrapper
      ;
    runtime = launchRuntime gpu.runtime;
    urlSchemeOpenCommands = ''
      exec ${gpu.runtime.toolsPackage}/bin/wine \
        'C:\Program Files\Autodesk\AdskIdentityManager\Current\AdskIdentityManager.exe' "$callback_url"
    '';
    executableName = rtExecutableName;
    baseLayer = gpu.withRuntime application;
    extraPreLaunchCommands = ''
      ${builtins.readFile ../runtime/gpu-ray-tracing.sh}
      ${preLaunch gpu.runtime}
      ${builtins.readFile ../runtime/enable-gpu-renderer.sh}
    '';
  }) rtExecutableName
else
  application
