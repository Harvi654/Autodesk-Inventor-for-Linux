# Compile an original matrix-payload fixture and validate every exported shader.
# Autodesk's captured shader is used only for local QA and is not redistributed.
{ pkgs, vkd3d }:
pkgs.stdenv.mkDerivation {
  pname = "inventor-ray-payload-check";
  version = vkd3d.version;
  inherit (vkd3d) src patches;
  nativeBuildInputs = [
    pkgs.cmake
    pkgs.ninja
    pkgs.python3
    pkgs.directx-shader-compiler
  ];
  cmakeDir = "../subprojects/dxil-spirv";
  cmakeFlags = [ "-DCMAKE_POLICY_VERSION_MINIMUM=3.5" ];
  buildFlags = [ "dxil-spirv" ];
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    dxc -T lib_6_3 -Fo matrix-payload.dxil ${../tests/shaders/matrix-payload.hlsl}
    ./dxil-spirv matrix-payload.dxil --debug-all-entry-points --validate > validation.log 2>&1
    cat validation.log
    runHook postCheck
  '';
  installPhase = ''
    mkdir -p "$out"
    cp validation.log "$out/"
  '';
  dontFixup = true;
}
