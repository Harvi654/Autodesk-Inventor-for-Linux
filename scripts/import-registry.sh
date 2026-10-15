#!/bin/bash
# (Re)import registry/autodesk-full.reg into the existing prefix, as UTF-16.
#
# Fixes prefixes built before the UTF-16 import fix, where every string from
# the Windows export was stored as "F\0a\0l\0s\0e\0" instead of "False" and
# Inventor crashed in InfoCenter (FormatException ... not a valid Boolean).
# Safe to run again: values are overwritten with the same correct data.
#
# Usage: bash scripts/import-registry.sh

set -euo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

[ -f "$REG_FILE" ] || die "no registry export at $REG_FILE - run scripts/export-registry.sh"
[ -d "$WINEPREFIX" ] || die "no prefix at $WINEPREFIX"
command -v iconv >/dev/null || die "iconv not found"

KEY="HKCU\\Software\\Autodesk\\Inventor\\RegistryVersion$INV_REGMAJOR.0\\WS:409\\InfoCenter\\SearchResults"
sample() { wine reg query "$KEY" /v SearchAllLanguages 2>/dev/null | tr -d '\r' | grep -i SearchAllLanguages || echo "    (value not present)"; }

info "stopping Wine for this prefix"
wine_stop
info "before:"; sample
info "importing $(basename "$REG_FILE") ($(wc -l < "$REG_FILE") lines) as UTF-16..."
import_reg_file "$REG_FILE"
wine_stop
info "after:";  sample
ok "done - 'after' must show the full word (False/True), not a single letter"
