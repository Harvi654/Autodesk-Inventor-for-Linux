# DXVK's shared DXGI implementation, with safe estimated timing for virtual
# displays that do not report a refresh rate (for example Xvfb).
{ pkgs }:
pkgs.dxvk.dxvk64.overrideAttrs (old: {
  patches = (old.patches or [ ]) ++ [
    ../patches/gpu/dxvk-invalid-refresh.patch
    ../patches/gpu/dxvk-upstream-sharing-backport.patch
    ../patches/gpu/dxvk-shared-runtime-buffer.patch
    ../patches/gpu/dxvk-imported-resource-handle.patch
  ];
})
