{
  pkgs,
  year ? "2026",
}:
let
  sources = {
    "2026" = {
      archiveHash = "sha256-MrmMh4cTR0WEjLsWemrfT5hse0TgyVdq3cFV+Hhq7Sc=";
      updateVersion = "2026.4";
      updateHash = "sha256-FgzGtaqfOlYEa2FEBzC0PNE9LPxjJkCLKNue756luPI=";
    };
    "2027" = {
      archiveHash = "sha256-h6AZa9Ue6wRmlffS7uR32xYjeMXQMGBANwn1PQXbM/0=";
      updateVersion = "2027.1";
      updateHash = "sha256-3K0IZ/7jlDSmL4Ra233dI3YgR3TM0569GvqabO8ll6Y=";
    };
  };
  source = sources.${year};
  meta = {
    homepage = "https://www.autodesk.com/products/inventor/overview";
    license = pkgs.lib.licenses.unfree;
  };
  archive =
    (pkgs.requireFile {
      name = "Inventor_Professional_${year}_English_Win_64bit_db_002_002.7z";
      hash = source.archiveHash;
      message = ''
        Download Inventor Professional ${year} English using Autodesk's direct download.
        Add the original archive to the local store:
          nix-store --add-fixed sha256 Inventor_Professional_${year}_English_Win_64bit_db_002_002.7z
      '';
    }).overrideAttrs
      { inherit meta; };
  update =
    (pkgs.requireFile {
      name = "Inventor_${source.updateVersion}_Update.exe";
      hash = source.updateHash;
      message = ''
        Download the Inventor ${source.updateVersion} update from Autodesk and add it to the local store:
          nix-store --add-fixed sha256 Inventor_${source.updateVersion}_Update.exe
      '';
    }).overrideAttrs
      { inherit meta; };
  media =
    pkgs.runCommand "inventor-${year}-english-media"
      {
        nativeBuildInputs = [ pkgs._7zz ];
        inherit meta;
      }
      ''
        mkdir -p "$out"
        7zz x -y -o"$out" ${archive} > /dev/null
        test -f "$out/manifest/app.inventor.xml"
      '';
in
{
  inherit media update;
}
