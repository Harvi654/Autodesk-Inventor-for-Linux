{ pkgs }:
let
  archive = pkgs.requireFile {
    name = "Inventor_Professional_2026_English_Win_64bit_db_002_002.7z";
    hash = "sha256-MrmMh4cTR0WEjLsWemrfT5hse0TgyVdq3cFV+Hhq7Sc=";
    message = ''
      Download Inventor Professional 2026 English using Autodesk's direct download.
      Add the original archive to the local store:
        nix-store --add-fixed sha256 Inventor_Professional_2026_English_Win_64bit_db_002_002.7z
    '';
  };
  update = pkgs.requireFile {
    name = "Inventor_2026.4_Update.exe";
    hash = "sha256-FgzGtaqfOlYEa2FEBzC0PNE9LPxjJkCLKNue756luPI=";
    message = ''
      Download the Inventor 2026.4 update from Autodesk and add it to the local store:
        nix-store --add-fixed sha256 Inventor_2026.4_Update.exe
    '';
  };
  media =
    pkgs.runCommand "inventor-2026-english-media"
      {
        nativeBuildInputs = [ pkgs._7zz ];
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
