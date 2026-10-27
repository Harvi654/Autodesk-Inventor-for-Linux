# shellcheck shell=bash
# Inventor's Hydra renderer must be selected before its graphics device starts.
# This is separate from the UseGPURaytracing preference in GraphicsUtil.
inventor_gpu_year="${INVENTOR_YEAR:-${INV_YEAR:-2026}}"
inventor_gpu_registry_major=$((inventor_gpu_year - 1996))
wine reg add \
    "HKCU\\Software\\Autodesk\\Inventor\\RegistryVersion${inventor_gpu_registry_major}.0\\System\\Preferences\\Driver" \
    /v EnableHydra /t REG_DWORD /d 1 /f || exit 1

# Wine's EGL path cannot supply the alpha-capable window format required by
# Inventor's OpenGL capability probe on the tested NVIDIA/Xwayland stack.
wine reg add \
    'HKCU\Software\Wine\AppDefaults\Inventor.exe\X11 Driver' \
    /v UseEGL /t REG_SZ /d N /f || exit 1
