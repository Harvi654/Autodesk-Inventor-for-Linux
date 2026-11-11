{
  lib,
  wineWow64Packages,
  fetchurl,
  # The winum source at the release tag (flake input "winum", see flake.nix).
  winum,
}:
let
  # Release this project uses; wine/version.env names the same one and the
  # flake check "winum-pin" fails when the two disagree.
  winumEnv = builtins.readFile "${winum}/wine/version.env";
  envValue =
    key:
    let
      m = builtins.match ".*\n${key}=([^\n]*)\n.*" ("\n" + winumEnv + "\n");
    in
    if m == null then throw "winum wine/version.env has no ${key}" else builtins.head m;
  wineVersion = envValue "WINE_VERSION";
  winumBuild = envValue "WINUM_BUILD";
  # patches/series of winum: the patches of a normal winum build, in order.
  # Nothing else in winum's patches/ (candidates, debug) is applied.
  series = lib.filter (line: line != "" && !lib.hasPrefix "#" line) (
    map lib.trim (lib.splitString "\n" (builtins.readFile "${winum}/patches/series"))
  );
in
(wineWow64Packages.unstableFull.override {
  embedInstallers = true;
}).overrideAttrs
  (old: {
    pname = "winum";
    version = "${wineVersion}-${winumBuild}";
    src = fetchurl {
      url = "https://dl.winehq.org/wine/source/11.x/wine-${wineVersion}.tar.xz";
      hash = "sha256-6sjKRI+cAIf5YwJrTcJ20eK3+7ZAVu3Ak+Wbu35W/ig=";
    };
    patches = (old.patches or [ ]) ++ map (name: "${winum}/patches/${name}") series;
    passthru = (old.passthru or { }) // {
      inherit wineVersion winumBuild series;
    };
  })
