#!/bin/bash
# Autodesk Inventor on Linux - set up with one command:
#
#   bash <(curl -fsSL https://raw.githubusercontent.com/Harvi654/Autodesk-Inventor-for-Linux/main/get.sh)
#
# What it does (read it first if you like - that is the point of this comment):
#   1. installs git if it is missing (pacman / apt / dnf, asks for your password)
#   2. downloads this project into ~/inventor-on-linux (the newest release),
#      or updates it if it is already there
#   3. starts the graphical installer (scripts/install-gui.sh); without a
#      graphical session it tells you the terminal command instead
# Nothing else is downloaded or changed by this script.
#
# INV_DIR=...         another folder than ~/inventor-on-linux
# INV_CHANNEL=main    the newest development state instead of the newest release

set -euo pipefail
# Everything runs from main() at the very end: if the download is cut off, a
# half-received script is a syntax error instead of a half-run install.
main() {
    REPO_URL="https://github.com/Harvi654/Autodesk-Inventor-for-Linux.git"
    DIR="${INV_DIR:-$HOME/inventor-on-linux}"
    CHANNEL="${INV_CHANNEL:-release}"

    say() { printf '\n==> %s\n' "$*"; }
    die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

    [ "$EUID" -ne 0 ] || die "run this as your normal user, not with sudo"
    [ "$(uname -m)" = x86_64 ] || die "Inventor needs an x86_64 (64-bit Intel/AMD) computer"

    if ! command -v git >/dev/null; then
        say "Installing git"
        . /etc/os-release
        case " ${ID:-} ${ID_LIKE:-} " in
            *" arch "*)                 sudo pacman -S --needed --noconfirm git ;;
            *" debian "*|*" ubuntu "*)  sudo apt-get update && sudo apt-get install -y git ;;
            *" fedora "*)               sudo dnf install -y git ;;
            *) die "install git with your package manager, then run this again" ;;
        esac
    fi

    if [ -d "$DIR/.git" ]; then
        say "Updating $DIR"
        if [ -f "$DIR/scripts/update-project.sh" ]; then bash "$DIR/scripts/update-project.sh"
        else git -C "$DIR" pull --ff-only; fi
    elif [ -e "$DIR" ]; then
        die "$DIR exists but is not a git checkout of this project - move it away or set INV_DIR"
    else
        say "Downloading the project into $DIR"
        git clone --quiet "$REPO_URL" "$DIR"
        tag="$(git -C "$DIR" tag -l 'v*' --sort=-v:refname | head -1)"
        # the newest release - if it already has the graphical installer
        if [ "$CHANNEL" = release ] && [ -n "$tag" ] && git -C "$DIR" cat-file -e "$tag:scripts/install-gui.sh" 2>/dev/null; then
            git -C "$DIR" -c advice.detachedHead=false checkout --quiet "$tag"
            echo "    release $tag"
        else
            echo "    newest development state (main)"
        fi
    fi

    if [ -n "${WAYLAND_DISPLAY:-}${DISPLAY:-}" ]; then
        say "Starting the installer"
        exec bash "$DIR/scripts/install-gui.sh"
    fi
    say "No graphical session - install from the terminal:"
    echo "    cd $DIR && bash scripts/install.sh ~/Downloads/<folder with Autodesk's download>"
}

main "$@"
