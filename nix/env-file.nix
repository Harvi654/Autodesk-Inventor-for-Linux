# Reads KEY=VALUE settings files (scripts/lib/bsdtar.env) the way
# install-from-image.py's read_env_file reads them: it strips each line, skips
# blank lines, `#` lines and lines without `=`, splits at the first `=`,
# strips key and value, strips quotes from both ends of the value, and keeps
# the last of duplicate keys.
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
# listToAttrs keeps the first of duplicate names, so the list is reversed to
# make the last one win.
lib.listToAttrs (lib.reverseList (map entry wanted))
