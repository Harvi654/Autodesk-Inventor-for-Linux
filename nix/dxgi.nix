# DXVK's shared DXGI implementation, with safe estimated timing for virtual
# displays that do not report a refresh rate (for example Xvfb).
{ pkgs }:
pkgs.dxvk.dxvk64.overrideAttrs (old: {
  patches = (old.patches or [ ]) ++ [
    ./dxvk-invalid-refresh.patch
    ./dxvk-upstream-sharing-backport.patch
    ./dxvk-shared-runtime-buffer.patch
    ./dxvk-imported-resource-handle.patch
  ];
})
