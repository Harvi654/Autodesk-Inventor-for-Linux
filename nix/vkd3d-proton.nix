{ pkgs, wine }:
# Nixpkgs' default output is a Linux-native library. Wine needs PE DLLs.
(pkgs.pkgsCross.mingwW64.vkd3d-proton.override { inherit wine; }).overrideAttrs (old: {
  pname = "vkd3d-proton-windows";
  # Aurora copies transform matrices through long-vector ray payloads.
  patches = (old.patches or [ ]) ++ [
    ../patches/gpu/vkd3d-ray-payload.patch
    ../patches/gpu/vkd3d-wine-shared-metadata.patch
  ];
  # D3DKMT declarations are supplied by the matching Wine package.
  NIX_CFLAGS_COMPILE = (old.NIX_CFLAGS_COMPILE or "") + " -idirafter ${wine}/include/wine/windows";
  buildInputs = (old.buildInputs or [ ]) ++ [ pkgs.pkgsCross.mingwW64.windows.pthreads ];
  meta = old.meta // {
    platforms = [ "x86_64-windows" ];
  };
})
