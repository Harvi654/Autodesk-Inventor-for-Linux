# shellcheck shell=bash
# Inventor's Hydra renderer must be selected before its graphics device starts.
# This is separate from the UseGPURaytracing preference in GraphicsUtil.
wine reg add \
    'HKCU\Software\Autodesk\Inventor\RegistryVersion30.0\System\Preferences\Driver' \
    /v EnableHydra /t REG_DWORD /d 1 /f || exit 1
