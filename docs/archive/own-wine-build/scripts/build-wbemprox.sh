#!/bin/bash
# Kept for compatibility: same as  bash scripts/build-wine-dll.sh wbemprox [options]
exec bash "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/build-wine-dll.sh" wbemprox "$@"
