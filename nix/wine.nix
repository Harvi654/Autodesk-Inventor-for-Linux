{
  lib,
  wineWow64Packages,
  fetchurl,
  # The winum source at the release tag (flake input "winum", see flake.nix).
  winum,
  # Topics under winum's patches/candidates/ to test on top of the series
  # (each applied in the order of its own series file). Empty for a normal
  # build: candidates are never part of a release.
  candidates ? [ ],
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
  readSeries =
    file:
    lib.filter (line: line != "" && !lib.hasPrefix "#" line) (
      map lib.trim (lib.splitString "\n" (builtins.readFile file))
    );
  candidatePatches = lib.concatMap (
    topic:
    map (name: "${winum}/patches/candidates/${topic}/${name}") (
      readSeries "${winum}/patches/candidates/${topic}/series"
    )
  ) candidates;
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
    patches = (old.patches or [ ]) ++ map (name: "${winum}/patches/${name}") series
      ++ candidatePatches;
    passthru = (old.passthru or { }) // {
      inherit wineVersion winumBuild series candidates;
    };
  })
