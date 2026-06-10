#!/bin/bash
# Phase 0: Environment Setup for Inventor 2026 on WINE
# Run this script with: sudo bash ~/Projects/Inventor\ on\ linux/scripts/phase0-setup.sh

set -e

echo "=== Phase 0: Installing prerequisites ==="

echo "[1/3] Installing DXVK..."
pacman -S --noconfirm --needed dxvk-mingw-git

echo "[2/3] Installing hivex (for Windows registry extraction)..."
pacman -S --noconfirm --needed hivex

echo "[3/3] Resetting faillock (clearing failed sudo attempts)..."
faillock --user lachlan --reset

echo ""
echo "=== Phase 0 complete! ==="
echo "Installed: dxvk-mingw-git, hivex"
echo "Cleared: faillock entries for lachlan"
