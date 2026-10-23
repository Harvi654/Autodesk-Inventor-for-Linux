# Build just the PE OpenGL implementation against the exact runtime Wine source.
# Keeping this as a runtime layer avoids rebuilding the immutable Autodesk install.
# Use runtimeWine for launchers: Wine searches its own builtin directory before
# WINEDLLPATH. The immutable Autodesk installation keeps using the original Wine.
{ pkgs, wine }:
let
  dll = wine.overrideAttrs (old: {
    pname = "wine-inventor-opengl32";
    patches = (old.patches or [ ]) ++ [ ../patches/gpu/wine-opengl-require-alpha.patch ];
    buildPhase = ''
      runHook preBuild
      make -j"$NIX_BUILD_CORES" dlls/opengl32/x86_64-windows/opengl32.dll
      runHook postBuild
    '';
    installPhase = ''
      runHook preInstall
      install -Dm644 dlls/opengl32/x86_64-windows/opengl32.dll "$out/bin/opengl32.dll"
      runHook postInstall
    '';
    preInstall = "";
    postInstall = "";
    doCheck = false;
    doInstallCheck = false;
    # The PE DLL has no Unix RPATH or executable wrapper to fix up.
    dontFixup = true;
  });
  runtimeWine =
    pkgs.runCommand "wine-inventor-opengl-runtime-${wine.version}"
      {
        inherit (wine) version meta;
        pname = "wine-inventor-opengl-runtime";
      }
      ''
        bash ${../runtime/assemble-wine-opengl.sh} ${wine} ${dll}/bin/opengl32.dll "$out"
      '';
in
{
  inherit dll runtimeWine;
}
