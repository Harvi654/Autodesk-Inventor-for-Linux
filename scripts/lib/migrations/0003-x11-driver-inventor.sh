# shellcheck shell=bash
# Step 0003: two X11 driver settings for Inventor.exe only
# (HKCU\Software\Wine\AppDefaults\Inventor.exe\X11 Driver):
#   UseEGL=N               GLX, the path GPU ray tracing was tested on
#   ClientSideWithRender=N no XRender 2D drawing: after GPU ray tracing the
#                          status bar text otherwise stays under new text
# docs/arch-hyprland.md, "GPU ray tracing" and "Status bar: old text stays".
MIG_DESC="X11 driver for Inventor.exe: UseEGL=N, ClientSideWithRender=N"

_MIG_X11_KEY='HKCU\Software\Wine\AppDefaults\Inventor.exe\X11 Driver'

mig_needed() {
    [ "$(mig_reg_get "$_MIG_X11_KEY" UseEGL)" != N ] ||
        [ "$(mig_reg_get "$_MIG_X11_KEY" ClientSideWithRender)" != N ]
}

mig_apply() {
    wine_reg_add "$_MIG_X11_KEY" /v UseEGL /t REG_SZ /d N
    wine_reg_add "$_MIG_X11_KEY" /v ClientSideWithRender /t REG_SZ /d N
    wine_stop
    ! mig_needed || { err "the X11 driver values did not stick"; return 1; }
}
