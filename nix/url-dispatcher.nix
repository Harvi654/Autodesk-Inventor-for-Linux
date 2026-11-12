# The adskidmgr:// handler for several Inventor releases. The scheme is one for
# all of them, so the callback goes to the release whose session is running:
# each launcher's forward-only mode (--nix-overlayfs-forward-url) hands it to
# its running session, or exits with status 3 when none runs. Only when no
# release runs does the newest one start with the callback. Any other failure
# of a forward is reported and ends the dispatch: a running release could not
# take its callback, and giving it to another release or starting one would
# hide that.
{ lib, writeShellScript }:
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
    status=0
    ${launcher.exe} --nix-overlayfs-forward-url "$url" || status=$?
    case "$status" in
      0) exit 0 ;;
      3) ;;
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
