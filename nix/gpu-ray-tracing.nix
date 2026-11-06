{
  pkgs,
  overlayfsLib,
  modules,
  wine,
}:
let
  opengl32 = import ./wine-opengl32.nix { inherit pkgs wine; };
  runtime = modules.runtime // {
    toolsPackage = opengl32.runtimeWine;
    mkSession =
      args:
      let
        session = modules.runtime.mkSession args;
      in
      session
      // {
        buildInputs = map (
          package:
          if toString package == toString modules.runtime.toolsPackage then opengl32.runtimeWine else package
        ) session.buildInputs;
        commands = session.commands // {
          wine = "${opengl32.runtimeWine}/bin/wine";
          wine64 = "${opengl32.runtimeWine}/bin/wine";
          wineserver = "${opengl32.runtimeWine}/bin/wineserver";
          wineboot = "${opengl32.runtimeWine}/bin/wineboot";
          winecfg = "${opengl32.runtimeWine}/bin/winecfg";
        };
      };
  };
  vkd3d = import ./vkd3d-proton.nix {
    inherit pkgs;
    wine = modules.runtime.toolsPackage;
  };
  layer =
    pkgs.runCommand "inventor-vkd3d-${vkd3d.version}"
      {
        pname = "inventor-vkd3d";
        inherit (vkd3d) version;
        nativeBuildInputs = [
          pkgs.bash
          pkgs.findutils
        ];
      }
      ''
        bash ${../runtime/install-vkd3d.sh} ${vkd3d} "$out"
      '';
  probe = pkgs.pkgsCross.mingwW64.stdenv.mkDerivation {
    pname = "inventor-dxr-check";
    version = "1";
    src = ../runtime;
    dontConfigure = true;
    buildPhase = ''
      $CC -std=c11 -O2 -Wall -Wextra -static dxr-check.c -o dxr-check.exe -lopengl32 -lgdi32
      $CC -std=c11 -O2 -Wall -Wextra -static pixel-format-check.c -o pixel-format-check.exe -lopengl32 -lgdi32
      $CC -std=c11 -O2 -Wall -Wextra -static shared-texture-check.c -o shared-texture-check.exe
    '';
    installPhase = ''
      install -Dm755 dxr-check.exe "$out/drive_c/dxr-check.exe"
      install -Dm755 pixel-format-check.exe "$out/drive_c/pixel-format-check.exe"
      install -Dm755 shared-texture-check.exe "$out/drive_c/shared-texture-check.exe"
    '';
  };
  dxgi =
    let
      package = import ./dxgi.nix { inherit pkgs; };
    in
    pkgs.runCommand "inventor-dxr-dxgi"
      {
        pname = "inventor-dxr-dxgi";
        version = pkgs.dxvk.version;
      }
      ''
        install -Dm644 ${package}/bin/dxgi.dll "$out/drive_c/windows/system32/dxgi.dll"
        install -Dm644 ${package}/bin/d3d11.dll "$out/drive_c/windows/system32/d3d11.dll"
      '';
  dependency = overlayfsLib.mkOverlayfsPackage {
    basePackage = layer;
    executableName = "";
    executablePath = "";
    passthru.runtimeEnvVars = { };
  };
  dxgiDependency = overlayfsLib.mkOverlayfsPackage {
    basePackage = dxgi;
    executableName = "";
    executablePath = "";
    passthru.runtimeEnvVars = { };
  };
  runtimeLayer = pkgs.runCommand "inventor-gpu-runtime" { } ''
    mkdir -p "$out"
    cp -r ${layer}/. "$out/"
    chmod -R u+w "$out"
    cp -r ${dxgi}/. "$out/"
  '';
  # The application already contains DXGI. A replacement must be above it,
  # rather than added as a lower-priority dependency of the application.
  withRuntime = application: {
    basePackage = runtimeLayer // {
      inherit (application.basePackage) pname version;
    };
    overlayDependencies = application.overlayDependencies ++ [ application ];
    runtimeEnvVars = application.runtimeEnvVars;
  };
  probeWine = pkgs.writeShellScript "dxr-check-wine" ''
    export INV_WINE=${runtime.toolsPackage}/bin/wine
    export INV_WINESERVER=${runtime.toolsPackage}/bin/wineserver
    exec ${pkgs.bash}/bin/bash ${../runtime/wine-session.sh} "$@"
  '';
  probeRuntime = runtime // {
    mkSession =
      args:
      let
        session = runtime.mkSession args;
      in
      session
      // {
        commands = session.commands // {
          wine = "${probeWine}";
        };
      };
  };
  probeDependency = overlayfsLib.mkOverlayfsPackage {
    basePackage = probe;
    executableName = "";
    executablePath = "";
    passthru.runtimeEnvVars = { };
  };
  mkCheck =
    {
      baseLayer,
      extraDependencies ? [ ],
      workingDirectory ? null,
      executableName ? "inventor-dxr-check",
      executablePath ? "/drive_c/dxr-check.exe",
    }:
    overlayfsLib.composeWindowsLayers {
      runtime = probeRuntime;
      packageName = "inventor-dxr-check";
      inherit executableName executablePath;
      hostIntegration = false;
      managedRuntime = "disabled";
      stateMode = "ephemeral";
      inherit baseLayer workingDirectory;
      overlayDependencies = [
        dependency
        dxgiDependency
      ]
      ++ extraDependencies;
      runtimeEnvVars.WINEDLLOVERRIDES = "dxgi,d3d11,d3d12,d3d12core=n;winemenubuilder.exe=d";
      extraPreLaunchCommands = ''
        ${(overlayfsLib.mkGraphicsBootstrap {
          inherit runtime;
          defaultMode = "system";
        }).extraPreLaunchCommands
        }
        ${builtins.readFile ../runtime/gpu-ray-tracing.sh}
        # Match Inventor's GLX capability probe in this ephemeral diagnostic prefix.
        wine reg add 'HKCU\Software\Wine\X11 Driver' /v UseEGL /t REG_SZ /d N /f
      '';
    };
in
{
  inherit
    vkd3d
    opengl32
    runtime
    probe
    dependency
    dxgiDependency
    withRuntime
    ;
  check = mkCheck {
    baseLayer = {
      basePackage = probe;
      overlayDependencies = [ ];
      runtimeEnvVars = { };
    };
  };
  checkPixelFormat = mkCheck {
    baseLayer = {
      basePackage = probe;
      overlayDependencies = [ ];
      runtimeEnvVars = { };
    };
    executableName = "inventor-pixel-format-check";
    executablePath = "/drive_c/pixel-format-check.exe";
  };
  checkSharedTexture = mkCheck {
    baseLayer = {
      basePackage = probe;
      overlayDependencies = [ ];
      runtimeEnvVars = { };
    };
    executableName = "inventor-shared-texture-check";
    executablePath = "/drive_c/shared-texture-check.exe";
  };
  checkApplication =
    application:
    mkCheck {
      baseLayer = withRuntime application;
      extraDependencies = [ probeDependency ];
      workingDirectory = "/drive_c/Program Files/Autodesk/Inventor 2026/Bin";
    };
}
