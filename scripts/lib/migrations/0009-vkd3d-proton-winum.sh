# shellcheck shell=bash
# Step 0009: vkd3d-proton (Direct3D 12) from winum's build,
# vkd3d-proton-3.0.1-winum-1: upstream 3.0.1 plus winum's ray tracing
# payload fix (github.com/Harvi654/winum, gpu/vkd3d-proton/README.md),
# pinned and SHA-256 checked (VKD3D_* in common.sh). The NixOS package
# uses the same archive, so both installations run the same d3d12.dll and
# d3d12core.dll. Before 2026-11-16 the installer put upstream's 3.0.1
# release in place.
# Only with INV_VKD3D=pinned (the default): INV_VKD3D=off keeps Wine's own
# d3d12, and a prefix whose DLLs are already the pinned ones is left alone.
# The old DLLs go to the backup. Offline at a launcher start the step is
# put off (MIG_DEFER), never blocking Inventor's start.
MIG_DESC="vkd3d-proton: winum's build of 3.0.1 (d3d12, d3d12core), as in the NixOS package"
MIG_BACKUP="drive_c/windows/system32/d3d12.dll drive_c/windows/system32/d3d12core.dll drive_c/windows/syswow64/d3d12.dll drive_c/windows/syswow64/d3d12core.dll"

mig_needed() { [ "$INV_VKD3D" = pinned ] && ! vkd3d_ok; }

mig_apply() {
    fetch_vkd3d || return $?
    install_vkd3d
    vkd3d_ok || die "d3d12.dll/d3d12core.dll in the prefix are not those of vkd3d-proton $VKD3D_VER"
}
