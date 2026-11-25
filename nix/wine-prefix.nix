# Whether a Wine patch changes what a Wine prefix contains, rather than only
# code. Inventor's layers are built with one Wine and run with another
# (nix-overlayfs launchRuntime); the prefix is not updated at runtime, so a
# patch that changes prefix contents only takes effect when the layers are
# rebuilt with it (installWineCandidates in flake.nix).
#
# A heuristic over the patch text: changes to loader/wine.inf (registry,
# files, fake DLLs), to COM registration scripts (.rgs, written into the
# registry when the prefix is created), and modules added or removed (a new or
# deleted dlls/*/Makefile.in or programs/*/Makefile.in). Anything else that
# changes the prefix has to be put into installWineCandidates by hand.
{ lib }:
{
  changesPrefix =
    text:
    let
      lines = lib.splitString "\n" text;
      pairs = lib.zipLists lines (lib.drop 1 lines);
      moduleMakefile = path: builtins.match "(dlls|programs)/[^/]+/Makefile[.]in" path != null;
      addsOrRemovesModule = lib.any (
        pair:
        (
          pair.fst == "--- /dev/null"
          && lib.hasPrefix "+++ b/" pair.snd
          && moduleMakefile (lib.removePrefix "+++ b/" pair.snd)
        )
        || (
          lib.hasPrefix "--- a/" pair.fst
          && pair.snd == "+++ /dev/null"
          && moduleMakefile (lib.removePrefix "--- a/" pair.fst)
        )
      ) pairs;
      touches =
        pattern:
        lib.any (
          line: lib.hasPrefix "+++ b/" line && builtins.match pattern (lib.removePrefix "+++ b/" line) != null
        ) lines;
    in
    touches "loader/wine[.]inf([.]in)?" || touches ".*[.]rgs" || addsOrRemovesModule;
}
