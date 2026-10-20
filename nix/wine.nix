{
  lib,
  wineWow64Packages,
  fetchurl,
}:
(wineWow64Packages.unstableFull.override {
  embedInstallers = true;
}).overrideAttrs
  (old: {
    pname = "wine-inventor";
    version = "11.20";
    src = fetchurl {
      url = "https://dl.winehq.org/wine/source/11.x/wine-11.20.tar.xz";
      hash = "sha256-6sjKRI+cAIf5YwJrTcJ20eK3+7ZAVu3Ak+Wbu35W/ig=";
    };
    patches =
      (old.patches or [ ])
      ++ map (name: ../patches + "/${name}") (
        lib.filter (name: lib.hasSuffix ".patch" name) (builtins.attrNames (builtins.readDir ../patches))
      );
  })
