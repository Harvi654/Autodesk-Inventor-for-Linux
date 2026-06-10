#!/bin/bash
set -e

# Autodesk Inventor 2026 on Linux - New Machine Setup Script
# This script sets up Inventor from a pre-built Wine prefix backup.
#
# Prerequisites:
#   - Linux with kernel 6.x+ (tested on CachyOS)
#   - Wine 11.4+ installed (pacman -S wine / apt install wine)
#   - DXVK installed (pacman -S dxvk / setup_dxvk)
#   - mingw-w64-gcc installed (for building wbemprox patch)
#   - Vulkan drivers for your GPU
#   - ImageMagick (optional, for icon extraction)
#   - A valid Autodesk Inventor 2026 license (SSO login required)
#
# Usage:
#   1. Extract the backup tarball
#   2. Run this script: bash install-on-new-machine.sh
#   3. Launch: bash launch-inventor.sh (or use desktop entry)
#
# Files expected in the same directory as this script:
#   - wine-prefix-inventor2026.tar.zst (the Wine prefix)
#   - wbemprox-patch/ (Wine source patch for Win32_TimeZone)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
WINEPREFIX="$HOME/.wine-inventor2026"

echo "============================================"
echo " Autodesk Inventor 2026 on Linux Installer"
echo "============================================"
echo ""
echo "Project dir: $PROJECT_DIR"
echo "Wine prefix: $WINEPREFIX"
echo ""

# Check prerequisites
echo "[1/8] Checking prerequisites..."
MISSING=""
command -v wine >/dev/null || MISSING="$MISSING wine"
command -v wineserver >/dev/null || MISSING="$MISSING wineserver"
command -v wineboot >/dev/null || MISSING="$MISSING wineboot"

if [ -n "$MISSING" ]; then
    echo "ERROR: Missing required packages:$MISSING"
    echo "Install with: sudo pacman -S wine  (or your distro's equivalent)"
    exit 1
fi

WINE_VER=$(wine --version 2>/dev/null | head -1)
echo "  Wine: $WINE_VER"
echo "  GPU: $(lspci 2>/dev/null | grep -i 'vga\|3d' | head -1 | sed 's/.*: //')"
echo ""

# Check for existing prefix
if [ -d "$WINEPREFIX" ]; then
    echo "WARNING: Wine prefix already exists at $WINEPREFIX"
    read -p "  Overwrite? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 1
    fi
    echo "  Killing existing wineserver..."
    WINEPREFIX="$WINEPREFIX" wineserver -k 2>/dev/null; sleep 2
fi

# Extract prefix
echo "[2/8] Extracting Wine prefix..."
TARBALL="$PROJECT_DIR/wine-prefix-inventor2026.tar.zst"
if [ ! -f "$TARBALL" ]; then
    # Try alternate names
    TARBALL=$(ls "$PROJECT_DIR/"*FULL*.tar.zst 2>/dev/null | head -1)
fi
if [ ! -f "$TARBALL" ]; then
    echo "ERROR: Cannot find Wine prefix tarball."
    echo "  Expected: $PROJECT_DIR/wine-prefix-inventor2026.tar.zst"
    echo "  Or any *FULL*.tar.zst in $PROJECT_DIR/"
    exit 1
fi

echo "  Extracting $(du -h "$TARBALL" | cut -f1) archive..."
cd "$HOME"
tar xf "$TARBALL" --zstd
echo "  Extracted to $WINEPREFIX"

# Verify prefix
if [ ! -d "$WINEPREFIX/drive_c/Program Files/Autodesk/Inventor 2026" ]; then
    echo "ERROR: Prefix extraction failed - Inventor not found"
    exit 1
fi

# Build and install wbemprox patch
echo "[3/8] Building Wine wbemprox patch (adds Win32_TimeZone WMI class)..."
WINE_SOURCE="/tmp/wine-source-for-wbemprox"
if [ ! -d "$WINE_SOURCE" ]; then
    echo "  Downloading Wine source..."
    # Extract version number
    WINE_VER_NUM=$(echo "$WINE_VER" | grep -oP '[\d.]+' | head -1)
    WINE_MAJOR=$(echo "$WINE_VER_NUM" | cut -d. -f1)
    cd /tmp
    curl -LO "https://dl.winehq.org/wine/source/${WINE_MAJOR}.x/wine-${WINE_VER_NUM}.tar.xz" 2>/dev/null
    tar xf "wine-${WINE_VER_NUM}.tar.xz"
    mv "wine-${WINE_VER_NUM}" "$WINE_SOURCE"
fi

# Apply the Win32_TimeZone patch
if [ -f "$PROJECT_DIR/patches/wbemprox-timezone.patch" ]; then
    echo "  Applying Win32_TimeZone patch..."
    cd "$WINE_SOURCE"
    patch -p1 < "$PROJECT_DIR/patches/wbemprox-timezone.patch" 2>/dev/null || true
elif [ -f "$PROJECT_DIR/scripts/apply-wbemprox-patch.sh" ]; then
    bash "$PROJECT_DIR/scripts/apply-wbemprox-patch.sh" "$WINE_SOURCE"
else
    echo "  WARNING: No wbemprox patch found. Win32_TimeZone will be missing."
    echo "  CPU ray tracing may produce flat results."
fi

# Build wbemprox
if [ -d "$WINE_SOURCE" ]; then
    cd "$WINE_SOURCE"
    if [ ! -f Makefile ]; then
        echo "  Configuring Wine build (minimal)..."
        ./configure --enable-win64 --without-x --without-freetype --without-fontconfig \
            --without-gstreamer --without-vulkan --without-opengl --without-alsa \
            --without-pulse --without-cups --without-dbus --without-usb \
            --without-v4l2 --without-wayland 2>/dev/null
    fi
    echo "  Building wbemprox.dll..."
    make -C dlls/wbemprox -j$(nproc) 2>/dev/null

    BUILT_DLL="$WINE_SOURCE/dlls/wbemprox/x86_64-windows/wbemprox.dll"
    if [ -f "$BUILT_DLL" ]; then
        echo "  Installing patched wbemprox.dll (requires sudo)..."
        SYSTEM_DLL="/usr/lib/wine/x86_64-windows/wbemprox.dll"
        sudo cp "$SYSTEM_DLL" "${SYSTEM_DLL}.original" 2>/dev/null
        sudo cp "$BUILT_DLL" "$SYSTEM_DLL"
        echo "  Installed! Original backed up as wbemprox.dll.original"
    else
        echo "  WARNING: Build failed. Continuing without wbemprox patch."
    fi
fi

# Set up DXVK in prefix
echo "[4/8] Setting up DXVK..."
if command -v setup_dxvk >/dev/null; then
    WINEPREFIX="$WINEPREFIX" setup_dxvk install 2>/dev/null || true
    echo "  DXVK installed"
else
    echo "  WARNING: setup_dxvk not found. Install DXVK manually."
fi

# Set up drive mappings
echo "[5/8] Setting up drive mappings..."
# Remove any stale drive mappings from the source machine
rm -f "$WINEPREFIX/dosdevices/d:" 2>/dev/null

echo "  Current block devices:"
lsblk -o NAME,SIZE,MOUNTPOINT | grep -v loop | head -10
echo ""
read -p "  Path to your Inventor data drive (or press Enter to skip): " DATA_DRIVE
if [ -n "$DATA_DRIVE" ] && [ -d "$DATA_DRIVE" ]; then
    ln -sf "$DATA_DRIVE" "$WINEPREFIX/dosdevices/d:"
    echo "  Mapped D: -> $DATA_DRIVE"
else
    echo "  Skipped. Map manually later: ln -sf /path/to/data ~/.wine-inventor2026/dosdevices/d:"
fi

# Set up OAuth2 callback handler
echo "[6/8] Setting up OAuth2 callback handler..."
mkdir -p ~/.local/bin ~/.local/share/applications

cat > ~/.local/share/applications/adskidmgr-handler.desktop << EOF
[Desktop Entry]
Type=Application
Name=Autodesk Identity Manager
Exec=$HOME/.local/bin/adskidmgr-callback %u
MimeType=x-scheme-handler/adskidmgr;
NoDisplay=true
EOF

ln -sf "$PROJECT_DIR/scripts/adskidmgr-callback.sh" ~/.local/bin/adskidmgr-callback
chmod +x ~/.local/bin/adskidmgr-callback
xdg-mime default adskidmgr-handler.desktop x-scheme-handler/adskidmgr 2>/dev/null
echo "  OAuth2 handler registered"

# Set up desktop entry
echo "[7/8] Creating desktop entry..."
ln -sf "$PROJECT_DIR/scripts/launch-inventor.sh" ~/.local/bin/launch-inventor
chmod +x ~/.local/bin/launch-inventor

# Extract icon
if command -v convert >/dev/null; then
    mkdir -p ~/.local/share/icons/hicolor/256x256/apps/
    convert "$WINEPREFIX/drive_c/Program Files/Autodesk/Inventor 2026/Bin/idv.ico[0]" \
        -thumbnail 256x256 -flatten \
        ~/.local/share/icons/hicolor/256x256/apps/autodesk-inventor-2026.png 2>/dev/null
fi

cat > ~/.local/share/applications/autodesk-inventor-2026.desktop << EOF
[Desktop Entry]
Type=Application
Name=Autodesk Inventor 2026
GenericName=CAD Application
Comment=Autodesk Inventor Professional 2026 (Wine)
Exec=$HOME/.local/bin/launch-inventor
Icon=autodesk-inventor-2026
Terminal=false
Categories=Graphics;Engineering;3DGraphics;
StartupWMClass=inventor.exe
Keywords=CAD;3D;Modeling;Engineering;Inventor;Autodesk;
EOF

update-desktop-database ~/.local/share/applications/ 2>/dev/null
echo "  Desktop entry created (search 'Inventor' in app launcher)"

# Final checks
echo "[8/8] Running final checks..."
export WINEPREFIX
wineserver -k 2>/dev/null; sleep 1

# Quick WMI test
wine cscript //NoLogo /dev/stdin 2>/dev/null << 'VBSEOF' || true
Set objWMI = GetObject("winmgmts:\\.\root\cimv2")
Set items = objWMI.ExecQuery("SELECT * FROM Win32_TimeZone")
If items.Count > 0 Then
    WScript.Echo "  Win32_TimeZone: OK (" & items.Count & " item)"
Else
    WScript.Echo "  Win32_TimeZone: MISSING (wbemprox patch needed)"
End If
VBSEOF

wineserver -k 2>/dev/null

echo ""
echo "============================================"
echo " Installation complete!"
echo "============================================"
echo ""
echo "Launch Inventor:"
echo "  bash $PROJECT_DIR/scripts/launch-inventor.sh"
echo ""
echo "Or search 'Inventor' in your app launcher."
echo ""
echo "First launch will require Autodesk SSO login via your web browser."
echo ""
echo "IMPORTANT: If Wine is updated, rebuild the wbemprox patch:"
echo "  cd $WINE_SOURCE && make -C dlls/wbemprox"
echo "  sudo cp dlls/wbemprox/x86_64-windows/wbemprox.dll /usr/lib/wine/x86_64-windows/"
echo ""
echo "See $PROJECT_DIR/README.md for full documentation."
