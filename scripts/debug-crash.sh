#!/bin/bash
# Find WHERE Inventor crashes: run it with Wine's exception (+seh) and DLL-load
# (+loaddll) tracing, then map every access violation (c0000005) to
# "module + RVA" - the same kind of address the README uses for OGSFactory.dll.
#
# Usage:
#   bash scripts/debug-crash.sh                  run Inventor traced, then analyze
#   bash scripts/debug-crash.sh --analyze [LOG]  analyze an existing traced log
#                                                (default: newest logs/inventor-*.log)
#
# The traced log is large (100+ MB is normal). Delete old ones when done.

set -uo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/common.sh"

if [ "${1:-}" = "--analyze" ]; then
    LOG="${2:-$(ls -t "$LOGDIR"/inventor-*.log 2>/dev/null | head -1)}"
else
    info "running Inventor with +seh,+loaddll tracing (slower than normal)..."
    WINEDEBUG="+pid,err+all,fixme-all,+seh,+loaddll" bash "$SCRIPTS_DIR/launch-inventor.sh" "$@"
    LOG="$(ls -t "$LOGDIR"/inventor-*.log 2>/dev/null | head -1)"
fi
[ -f "${LOG:-}" ] || die "no log found"
info "log: $LOG ($(du -h "$LOG" | cut -f1))"
echo

# Line formats (Wine 11, x86_64):
#   0130:0134:trace:loaddll:build_module Loaded L"C:\\...\\OGSFactory.dll" at 0000000180000000: native
#   0130:0134:trace:seh:dispatch_exception code=c0000005 flags=0 addr=000000018005A3B2 ip=18005a3b2 tid=0134
#    ...:trace:seh:dispatch_exception  info[0]=0000000000000000   (0 = read, 1 = write, 8 = execute)
#    ...:trace:seh:dispatch_exception  info[1]=0000000000000000   (address that was accessed)
LC_ALL=C awk '
function hex(s,    i, c, v) {
    v = 0; s = tolower(s)
    for (i = 1; i <= length(s); i++) { c = index("0123456789abcdef", substr(s, i, 1)); if (!c) break; v = v * 16 + c - 1 }
    return v
}
function module_of(pid, a,    i, best, bb) {
    best = ""; bb = -1
    for (i = 1; i <= nmod[pid]; i++)
        if (mbase[pid, i] <= a && mbase[pid, i] > bb) { bb = mbase[pid, i]; best = mname[pid, i] }
    # No size info in the log: an RVA above 256 MB means the address is not in
    # that module - usually code generated at runtime (.NET JIT).
    if (best == "" || a - bb > 268435456) return sprintf("%x (no module - .NET JIT code?)", a)
    return sprintf("%s+0x%x", best, a - bb)
}
{
    split($0, f, ":")
    pid = (f[2] ~ /^[0-9a-f][0-9a-f][0-9a-f][0-9a-f]$/) ? f[1] : "?"
}
/trace:loaddll:.* Loaded L"/ {
    name = $0; sub(/.* Loaded L"/, "", name); sub(/" at .*/, "", name)
    gsub(/\\\\/, "\\", name); n = split(name, parts, "\\"); short = parts[n]
    base = $0; sub(/.*" at /, "", base); sub(/:.*/, "", base)
    i = ++nmod[pid]; mbase[pid, i] = hex(base); mname[pid, i] = short
    next
}
/trace:seh:dispatch_exception code=c0000005 .* addr=/ {
    addr = $0; sub(/.* addr=/, "", addr); sub(/ .*/, "", addr)
    where = module_of(pid, hex(addr))
    pending = where; pline = NR; access = ""; target = ""
    next
}
pending != "" && /trace:seh:.* info\[0\]=/ { v = $0; sub(/.*info\[0\]=/, "", v); access = (hex(v) == 1) ? "write" : (hex(v) == 8 ? "execute" : "read"); next }
pending != "" && /trace:seh:.* info\[1\]=/ {
    v = $0; sub(/.*info\[1\]=/, "", v); target = v
    key = pending " (" access " of " target ")"
    if (!(key in count)) { order[++norder] = key; first[key] = pline }
    count[key]++
    pending = ""
    next
}
/ignoring exception c0000005/ { swallowed[++nsw] = NR ": " $0 " <- last AV: " (key ? key : "?") }
/Unhandled exception\./ && !unhandled { unhandled = NR ": " $0 }
END {
    print "== Access violations (c0000005), in order of first occurrence"
    if (!norder) print "   none traced"
    for (i = 1; i <= norder; i++) printf "   %4dx  %s   [first at line %d]\n", count[order[i]], order[i], first[order[i]]
    print ""
    print "== Swallowed by Wine inside a window callback (state is corrupt after this)"
    if (!nsw) print "   none"
    for (i = 1; i <= nsw; i++) print "   " swallowed[i]
    print ""
    print "== First unhandled .NET exception"
    print "   " (unhandled ? unhandled : "none")
}' "$LOG"

echo
info "How to read it: an AV in '.NET JIT code' reading 0000000000000000 followed by an"
info "unhandled NullReferenceException is a managed null dereference (the .NET stack trace"
info "is the real location). An AV inside a native DLL (module+RVA) is a native crash."
info "kernelbase.dll+0x4e95c is RaiseException - an exception re-thrown, not a new crash."
