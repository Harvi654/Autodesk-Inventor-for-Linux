#!/usr/bin/env bash
# End only the Wine server associated with this launcher's composed prefix.
set +e
"${INV_WINE:?}" "$@"
status=$?
"${INV_WINESERVER:?}" -k
exit "$status"
