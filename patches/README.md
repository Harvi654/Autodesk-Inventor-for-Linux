# Compatibility patches

- Top-level `*.patch` files target Wine. Both `nix/wine.nix` and the script-based
  Wine build discover these automatically.
- `libgsf/` contains the empty OLE stream fix used by the flake's libgsf overlay.
- `gpu/` contains opt-in GPU runtime patches for DXVK, vkd3d-proton, and Wine's
  separately built OpenGL DLL. The corresponding expressions in `nix/` select
  these explicitly; the normal Wine build does not apply them.
- `drafts/` contains unfinished upstream experiments, excluded from normal builds.
- `debug/` contains optional diagnostic patches, excluded from normal builds.

Keep patches for other projects and optional runtime variants in subdirectories
so Wine's automatic top-level patch discovery cannot apply them accidentally.
