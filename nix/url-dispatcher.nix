# The adskidmgr:// handler for several Inventor releases. The scheme is one for
# all of them, so the callback goes to the release whose session is running:
# each launcher's forward-only mode (--nix-overlayfs-forward-url) hands it to
# its running session. Exit statuses of a forward (nix-overlayfs, "URL
# schemes"):
#   0  delivered;
#   3  no session of that release was there: try the next release;
#   4  its session is starting or closing, the URL was taken back: ask the
#      same release again, a few times;
#   5  its session was there but ended before taking the URL: the callback
#      belongs to that release, so it is started with it.
# A 3 after a 4 from the same release means the same as 5 (its session went
# away meanwhile). Only when no release had a session does the newest one
# start with the callback. Any other failure, or 4 after the retries, is
# reported and ends the dispatch: handing the callback to another release, or
# starting one, would hide that a running release could not take it.
{
  lib,
  writeShellScript,
  # Forward attempts per release while it answers 4 (each waits up to
  # NIX_OVERLAYFS_URL_FORWARD_WAIT, 30 s by default, inside the launcher).
  retries ? 4,
}:
# Launcher executables, newest release first: [ { name = "2027"; exe = "..."; } ... ].
launchers:
assert lib.assertMsg (launchers != [ ]) "url-dispatcher: no launchers";
(writeShellScript "autodesk-inventor-open-url" ''
  url="''${1:-}"
  if [ -z "$url" ]; then
    echo "usage: autodesk-inventor-open-url adskidmgr://..." >&2
    exit 2
  fi
  ${lib.concatMapStrings (launcher: ''
    attempt=1
    was_busy=0
    while :; do
      status=0
      ${launcher.exe} --nix-overlayfs-forward-url "$url" || status=$?
      [ "$status" = 4 ] || break
      was_busy=1
      [ "$attempt" -lt ${toString retries} ] || break
      attempt=$((attempt + 1))
    done
    case "$status" in
      0) exit 0 ;;
      3) [ "$was_busy" = 0 ] || exec ${launcher.exe} "$url" ;;
      5) exec ${launcher.exe} "$url" ;;
      *)
        echo "Autodesk Inventor ${launcher.name}: could not hand the sign-in callback to its running session (status $status)" >&2
        exit "$status"
        ;;
    esac
  '') launchers}
  exec ${(builtins.head launchers).exe} "$url"
'').overrideAttrs
  (old: {
    passthru = (old.passthru or { }) // {
      inherit launchers;
    };
  })
