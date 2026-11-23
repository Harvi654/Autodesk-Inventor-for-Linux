# KEY=VALUE settings files (scripts/lib/bsdtar.env), read the way
# install-from-image.py's read_env_file reads them: lines stripped, blank and
# `#` lines and lines without `=` skipped, split at the first `=`, key and
# value stripped, quotes stripped from both ends of the value, the last of
# duplicate keys wins.
{ lib }:
path:
let
  lines = map lib.trim (lib.splitString "\n" (builtins.readFile path));
  wanted = lib.filter (line: line != "" && !(lib.hasPrefix "#" line) && lib.hasInfix "=" line) lines;
  unquote =
    value:
    let
      m = builtins.match "\"*(.*[^\"])?\"*" value;
    in
    if m == null || builtins.head m == null then "" else builtins.head m;
  entry =
    line:
    let
      m = builtins.match "([^=]*)=(.*)" line;
    in
    lib.nameValuePair (lib.trim (builtins.elemAt m 0)) (unquote (lib.trim (builtins.elemAt m 1)));
in
# listToAttrs keeps the first of duplicate names: reversed, the last wins.
lib.listToAttrs (lib.reverseList (map entry wanted))
