{
  pkgs,
  overlayfsLib,
  # Wine and layers the installation is built with (the winum release).
  modules,
  # Wine Inventor runs: a build of the same release, possibly with winum
  # candidates under test. Changing it rebuilds only the launcher.
  launchModules ? modules,
}:
{
  # A fixed-output derivation containing the original Autodesk install image.
  media,
  updates ? [ ],
  year ? "2026",
  version ? year,
  executableName ? if year == "2026" then "inventor" else "inventor-${year}",
  contentCenter ? true,
  # At every launch, make this release the user's adskidmgr:// handler
  # (~/.local/share/applications, ~/.config/mimeapps.list). The NixOS module
  # declares one handler for all releases instead and turns this off.
  registerHostUrlHandlers ? true,
  # Runtime layers for Direct3D (nix-overlayfs file layers, for example
  # modules.dxvkRelease { ... } or modules.vkd3d-proton.override { ... });
  # null = the pinned defaults below. Changing them rebuilds only the launcher.
  dxvkLayer ? null,
  vkd3dLayer ? null,
}@inventorArgs:
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
        # The same release with other mkInventor arguments, for example
        # `withArgs { registerHostUrlHandlers = false; }`.
        withArgs =
          extra:
          import ./inventor.nix {
            inherit
              pkgs
              overlayfsLib
              modules
              launchModules
              ;
          } (inventorArgs // extra);
        # The wrapper the launcher runs Wine through (checked by the flake).
        inherit launchWine;
      };
    });
  # Licensing and SSO stay alive after Inventor exits. End this prefix's Wine
  # session when the main process exits so overlayfs can unmount it cleanly.
  launchTools = launchModules.runtime.toolsPackage;
  launchWine = pkgs.writeShellScript "inventor-wine-session" ''
    set +e
    ${launchTools}/bin/wine "$@"
    status=$?
    ${launchTools}/bin/wineserver -k
    exit "$status"
  '';
  launchRuntime = launchModules.runtime // {
    mkSession =
      args:
      let
        session = launchModules.runtime.mkSession args;
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
  # tar.exe for the prefix (scripts/lib/bsdtar.env): libarchive's signed
  # Windows build of bsdtar, which the Electrical Catalog Browser's installer
  # needs; install-from-image.py takes it from DOWNLOAD_DIR.
  bsdtarArchive = pkgs.fetchurl {
    url = "https://github.com/libarchive/libarchive/releases/download/v3.5.3/libarchive-v3.5.3-win64.zip";
    sha256 = "81c45c31a31a7b49809b3625594c28a1afbcc18faa6ee1d2ab4e4328ba8ef736";
  };
  # Direct3D 8-11 and 12 on Vulkan, as runtime layers above the installation:
  # a new version rebuilds only the launcher. Their DLL overrides are in the
  # layers' registry, so the per-program exception the prefix setup writes
  # for msedgewebview2.exe (wined3d, Wine's d3d12) still applies.
  # (mkInventor's dxvkLayer / vkd3dLayer arguments replace them.)
  dxvk =
    if dxvkLayer != null then
      dxvkLayer
    else
      modules.dxvkRelease {
        version = "2.7.1";
        src = pkgs.fetchurl {
          url = "https://github.com/doitsujin/dxvk/releases/download/v2.7.1/dxvk-2.7.1.tar.gz";
          hash = "sha256-2Fznx59X7NdlqqG55wB8uHXm/en20zHfeZvOc9UTzoc=";
        };
      };
  # winum's build of vkd3d-proton 3.0.1 with the GPU ray tracing fixes
  # (gpu/vkd3d-proton/ in winum, docs/arch-hyprland.md "GPU ray tracing").
  vkd3dProton =
    if vkd3dLayer != null then
      vkd3dLayer
    else
      modules.vkd3d-proton.override {
        archiveVersion = "3.0.1-winum-1";
        archive = pkgs.fetchurl {
          url = "https://github.com/Harvi654/winum/releases/download/vkd3d-proton-3.0.1-winum-1/vkd3d-proton-3.0.1-winum-1.tar.zst";
          sha256 = "7d20a226388830a268943c6d0845e0e51f0569fd540df0e2f0153e31a838c8b7";
        };
      };
  webview2 =
    (overlayfsLib.mkWindowsPackage {
      inherit (modules) runtime;
      # Same base environment as the installation (no Wine Mono, see below).
      managedRuntime = "external";
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
  # Microsoft's .NET Framework 4.8 (3D PDF, Import CAD's Property Mapping) as
  # nix-overlayfs's dotnet-framework-4-8 layer below the installation, in
  # place of Wine Mono; the installer's own .NET step is skipped here. It
  # exports mscoree=native (dllOverrides) to the launcher.
  dotnet48 = modules.dotnet-framework-4-8;
  # The installation, built with the release Wine in the Nix sandbox. DXVK and
  # vkd3d-proton are not installed into it (INV_DXVK/INV_VKD3D=none).
  installed = overlayfsLib.mkWindowsPackage {
    inherit (modules) runtime;
    inherit version;
    # A base environment without Wine Mono: .NET comes from the dotnet48 layer.
    managedRuntime = "external";
    portableReparsePoints = true;
    pname = "inventor";
    packageName = "autodesk-inventor-${year}-installation";
    src = media;
    overlayDependencies = [
      webview2
      dotnet48
    ];
    unshareInstall = { session, ... }: ''
      set -euo pipefail
      export PATH=${lib.makeBinPath tools}:${modules.runtime.toolsPackage}/bin:$PATH
      export INV_YEAR=${lib.escapeShellArg year}
      export INV_WINE=system INV_SANDBOX=0 INV_DATA_DIR="" INV_FONTS=linux
      export INV_DXVK=none INV_VKD3D=none
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
      ln -s ${bsdtarArchive} "$DOWNLOAD_DIR/libarchive-v3.5.3-win64.zip"
      python3 "$TMPDIR/inventor-project/scripts/install-from-image.py" "$src" \
        --prefix "$WINEPREFIX" --prepared-prefix --preinstalled-webview2 --no-dotnet48 ${
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
      # .NET Framework 4.8 from the dotnet48 layer (3D PDF, Import CAD property mapping)
      test -f "$WINEPREFIX/drive_c/windows/Microsoft.NET/Framework64/v4.0.30319/clr.dll"
      test -f "$WINEPREFIX/drive_c/windows/Microsoft.NET/Framework/v4.0.30319/clr.dll"
    '';
  };
in
# The launcher: the installation with DXVK and vkd3d-proton above it, run on
# launchRuntime.
withInventorMeta (overlayfsLib.composeWindowsLayers {
  inherit (modules) runtime;
  inherit launchRuntime;
  managedRuntime = "external";
  packageName = "autodesk-inventor-${year}";
  baseLayer = {
    inherit (installed) basePackage;
    overlayDependencies = [
      webview2
      dotnet48
    ];
    runtimeEnvVars = { };
    requiredManagedRuntime = "external";
  };
  overlayDependencies = [
    dxvk
    vkd3dProton
  ];
  inherit executableName;
  executablePath = "/drive_c/Program Files/Autodesk/Inventor ${year}/Bin/Inventor.exe";
  workingDirectory = "/drive_c/Program Files/Autodesk/Inventor ${year}/Bin";
  runtimeEnvVars = {
    INVENTOR_YEAR = year;
    WINE_LARGE_ADDRESS_AWARE = "1";
  };
  # Merged with the layers' overrides (mscoree=n comes from the dotnet48 layer).
  dllOverrides = {
    msquic = "";
    "winemenubuilder.exe" = "";
  };
  urlSchemes = [ "adskidmgr" ];
  inherit registerHostUrlHandlers;
  entrypointWrapper = entrypoint: ''
    case "''${1:-}" in
      adskidmgr:*) exec ${entrypoint} --nix-overlayfs-open-url "$1" ;;
      *) exec ${entrypoint} "$@" ;;
    esac
  '';
  urlSchemeOpenCommands = ''
    exec ${launchTools}/bin/wine \
      'C:\Program Files\Autodesk\AdskIdentityManager\Current\AdskIdentityManager.exe' "$callback_url"
  '';
  extraPreLaunchCommands = ''
    export PATH=${launchTools}/bin:${
      lib.makeBinPath (
        tools
        ++ [
          pkgs.util-linux
          pkgs.fontconfig
        ]
      )
    }:$PATH
    ${builtins.readFile ./launch-lock.sh}
    ${(overlayfsLib.mkGraphicsBootstrap {
      inherit (launchModules) runtime;
      defaultMode = "system";
    }).extraPreLaunchCommands
    }
    ${builtins.readFile ./launch-fonts.sh}
    ${builtins.readFile ./launch-services.sh}
  '';
}) executableName
