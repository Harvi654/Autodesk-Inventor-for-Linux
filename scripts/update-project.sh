#!/bin/bash
# Update this project: to the newest release (vX.Y.Z tag) when it was set up
# by get.sh, or "git pull" when you work on a branch (e.g. main).
#
#   bash scripts/update-project.sh

set -euo pipefail
cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.."

# the scripts chmod +x each other - not a change worth blocking an update for
git config core.fileMode false
git fetch --quiet --tags origin
if git symbolic-ref -q HEAD >/dev/null; then
    echo "    on branch $(git symbolic-ref --short HEAD): git pull"
    git pull --ff-only
else
    latest="$(git tag -l 'v*' --sort=-v:refname | head -1)"
    current="$(git describe --tags --exact-match 2>/dev/null || git rev-parse --short HEAD)"
    if [ -z "$latest" ] || [ "$latest" = "$current" ]; then
        echo "    up to date ($current)"
    else
        git -c advice.detachedHead=false checkout --quiet "$latest"
        echo "    updated $current -> $latest"
    fi
fi
