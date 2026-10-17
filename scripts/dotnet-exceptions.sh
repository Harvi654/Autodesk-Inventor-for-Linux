#!/bin/bash
# List the .NET exceptions Inventor throws - also the ones it catches itself and
# only reports as "Unexpected failure while executing this command".
#
# Uses the .NET runtime's built-in EventPipe tracing (no extra tools): the
# runtime writes a .nettrace file with an ExceptionThrown event per exception,
# whose type and message are UTF-16 strings we can pull out with `strings`.
#
# Usage:
#   bash scripts/dotnet-exceptions.sh            run Inventor traced; reproduce the
#                                                problem, close Inventor, get the list
#   bash scripts/dotnet-exceptions.sh --analyze  list from the last trace again
#
# The trace holds exception messages only - no documents, no memory. Messages can
# contain file paths with your user name.

set -uo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

TRACE_DIR="$P_C/windows/temp/nettrace"
if [ "${1:-}" != "--analyze" ]; then
    rm -rf "$TRACE_DIR"; mkdir -p "$TRACE_DIR"
    export DOTNET_EnableEventPipe=1
    export DOTNET_EventPipeOutputPath='C:\windows\temp\nettrace\trace-{pid}.nettrace'
    # Microsoft-Windows-DotNETRuntime, keyword 0x8000 = exceptions, level 4
    export DOTNET_EventPipeConfig='Microsoft-Windows-DotNETRuntime:0x8000:4'
    info "Inventor runs with .NET exception tracing; reproduce the problem, then close Inventor"
    bash "$SCRIPTS_DIR/launch-inventor.sh" "$@"
fi

shopt -s nullglob
files=("$TRACE_DIR"/*.nettrace)
[ ${#files[@]} -gt 0 ] || die "no .nettrace written in $TRACE_DIR"
for f in "${files[@]}"; do
    echo "== $(basename "$f") ($(du -h "$f" | cut -f1))"
    # ExceptionThrown_V1 payload: type name, then message (UTF-16). Print each
    # exception type with the string that follows it, count duplicates.
    strings -el -n 6 "$f" | awk '
        /^System\.[A-Za-z.]*Exception$|^[A-Za-z_][A-Za-z0-9_.]*Exception$/ { if (t != "") print t " | "; t = $0; next }
        t != "" { print t " | " substr($0, 1, 200); t = ""; next }
        END { if (t != "") print t " | " }' \
        | sort | uniq -c | sort -rn | head -40
done
info "in order of occurrence, with the method that caught each one (last ${TAIL:-80} lines):"
# ExceptionThrown events carry type + message; the ExceptionCatchStart event
# that follows carries the name of the method whose catch block handled it -
# that tells which component swallowed the error.
strings -el -n 6 "${files[@]}" | grep -v -E '^(Microsoft-Windows-DotNETRuntime|EventPipe|Exception(Thrown|Catch|Filter|Finally)[A-Za-z_]*|ClrInstanceID|ExceptionType|ExceptionMessage|ExceptionEIP|ExceptionHRESULT|ExceptionFlags|EntryEIP|MethodID|MethodName)$' \
    | tail -"${TAIL:-80}" | cut -c1-220
