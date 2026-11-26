{
  lib,
  wineWow64Packages,
  fetchurl,
  # The winum source at a release tag (flake input "winum" or "winum-install",
  # see flake.nix).
  winum,
  # Topics under winum's patches/candidates/ to test on top of the series
  # (each applied in the order of its own series file). Empty for a normal
  # build: candidates are never part of a release.
  candidates ? [ ],
  # Where the candidates come from (the launch Wine's `winum`, possibly a
  # winum checkout; the flake checks use a fixture). Not read when there are
  # no candidates.
  candidatesSource ? winum,
}:
let
  # A file of a winum source. A local path (a checkout given with
  # --override-input, or a test fixture) stays a path: string interpolation
  # would need a store copy, which `nix flake check --no-build` (CI) does not
  # make. A flake input is already a store path.
  under = source: file: if builtins.isPath source then source + "/${file}" else "${source}/${file}";
  # The release, from winum's own wine/version.env; the flake check
  # "winum-pin" fails when it differs from the input's tag.
  winumEnv = builtins.readFile (under winum "wine/version.env");
  envValue =
    key:
    let
      m = builtins.match ".*\n${key}=([^\n]*)\n.*" ("\n" + winumEnv + "\n");
    in
    if m == null then throw "winum wine/version.env has no ${key}" else builtins.head m;
  wineVersion = envValue "WINE_VERSION";
  # SHA-256 of the Wine source tarball, as winum's release names it.
  wineSha256 = envValue "WINE_SHA256";
  winumBuild = envValue "WINUM_BUILD";
  # patches/series of winum: the patches of a normal winum build, in order.
  # Nothing else in winum's patches/ (candidates, debug) is applied.
  series = lib.filter (line: line != "" && !lib.hasPrefix "#" line) (
    map lib.trim (lib.splitString "\n" (builtins.readFile (under winum "patches/series")))
  );
  seriesPatches = map (name: under winum "patches/${name}") series;
  readSeries =
    file:
    lib.filter (line: line != "" && !lib.hasPrefix "#" line) (
      map lib.trim (lib.splitString "\n" (builtins.readFile file))
    );
  candidatePatches = lib.concatMap (
    topic:
    let
      directory = under candidatesSource "patches/candidates/${topic}";
    in
    map (name: under directory name) (readSeries (under directory "series"))
  ) candidates;
  # Which prefixes this Wine runs as built (nix-overlayfs compares it between
  # the Wine that built the layers and the one that runs them): the winum
  # release, plus a hash of the release series and candidate patches that
  # change prefix contents. The release series' patches are included so that a
  # winum checkout given as `winum` (to test candidates) that has the same
  # release name but changed prefix patches is refused rather than run.
  prefixChangingPatches = lib.filter (
    patch: (import ./wine-prefix.nix { inherit lib; }).changesPrefix (builtins.readFile patch)
  ) (seriesPatches ++ candidatePatches);
  prefixCompatibility =
    "winum-${wineVersion}-${winumBuild}"
    +
      lib.optionalString (prefixChangingPatches != [ ])
        "+${
          builtins.substring 0 16 (
            builtins.hashString "sha256" (lib.concatMapStrings builtins.readFile prefixChangingPatches)
          )
        }";
in
(wineWow64Packages.unstableFull.override {
  embedInstallers = true;
}).overrideAttrs
  (old: {
    pname = "winum";
    version = "${wineVersion}-${winumBuild}";
    src = fetchurl {
      url = "https://dl.winehq.org/wine/source/11.x/wine-${wineVersion}.tar.xz";
      sha256 = wineSha256;
    };
    patches = (old.patches or [ ]) ++ seriesPatches ++ candidatePatches;
    passthru = (old.passthru or { }) // {
      inherit
        wineVersion
        winumBuild
        series
        candidates
        prefixCompatibility
        ;
    };
  })
