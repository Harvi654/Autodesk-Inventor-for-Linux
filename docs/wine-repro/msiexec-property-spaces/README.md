# msiexec: a property value with a space, passed as one argument

**Result: not a Wine bug - Windows does the same** (measured 2026-11-16,
below).

Found 2026-11-16 by the installer completeness review: Inventor 2027's
`InvPrivate.msi` with `INSTALLDIR=C:\Program Files\Autodesk\Inventor 2027\`
ended at once with exit code 103 (= 1639, `ERROR_INVALID_COMMAND_LINE`).
Revit's earlier "MSI property values with a space fail" is the same.

## How it fails (read in Wine 11.20's source)

1. We run `wine msiexec /i X.msi /qn "INSTALLDIR=C:\Program Files\X"` -
   the property is ONE argument (Python's argv, or a quoted shell word).
2. Wine builds the Windows command line from the arguments
   (`dlls/ntdll/unix/env.c`, `build_command_line`): an argument with a
   space is put in quotes as a whole:
   `msiexec /i X.msi /qn "INSTALLDIR=C:\Program Files\X"`. This is the
   usual Windows convention (the C runtime and CommandLineToArgvW read it
   back as one argument).
3. Wine's msiexec splits its command line with its own `chomp`
   (`programs/msiexec/msiexec.c`), which keeps the quote characters: the
   argument becomes `"INSTALLDIR=C:\Program Files\X"` with the quotes.
4. `build_properties` quotes a value with a space once more and passes
   ` "INSTALLDIR="C:\Program Files\X""` to MsiInstallProduct.
5. `msi_parse_command_line` (`dlls/msi/action.c`) reads a property named
   `"INSTALLDIR` and an odd number of quotes, and returns
   ERROR_INVALID_COMMAND_LINE.

The form ODIS passes on Windows, `INSTALLDIR="C:\Program Files\X\"`,
goes through steps 3-5 correctly - but a Linux program cannot produce it
through step 2. install-from-image.py therefore writes such a command line
into a batch file and runs `wine cmd /c` on it (cmd hands the line to
msiexec unchanged).

## What Windows does - measured 2026-11-16

The same on Windows. Windows: the maintainer's Windows 10 test VM
(10.0.19045.6466, Windows Installer 5.0.19041.4651 - the VM used for tests
and patches, not the reference snapshot). Wine: winum-11.20-2, a fresh
prefix. The MSI is synthetic (`quotetest.wxs`, built with msitools'
`wixl`).

| Form | Wine 11.20 (winum-11.20-2) | Windows 10 |
|---|---|---|
| A `"INSTALLDIR=C:\quote test\a"` (one quoted argument) | 103 (= 1639), installs nothing | 1639, installs nothing (Windows Installer shows its usage dialog) |
| B the same with a trailing backslash | 1639, nothing | 1639, nothing |
| C `INSTALLDIR="C:\quote test\a\"` (ODIS's form; a batch file under Wine) | 0, `C:\quote test\a` | 0, `C:\quote test\a` |
| D `INSTALLDIR=C:\quotetest` (no space, control) | 0 | 0 |

**Conclusion: Wine behaves as Windows. msiexec accepts a property value
with a space only as `NAME="value"`, on Windows too;** a property passed as
one argument gets quoted as a whole by the usual argv convention (step 2)
and is rejected on both (steps 3-5 describe how Wine gets there; Windows
gets to the same result). **Not a Wine bug** - no report on
bugs.winehq.org. The batch file with `NAME="value"` in
install-from-image.py is the right design - the command line ODIS builds
on Windows - not a workaround for Wine.

## Running it

```bash
cd docs/wine-repro/msiexec-property-spaces
echo marker > marker.txt
wixl quotetest.wxs
export WINEPREFIX=/tmp/quotetest-prefix
mkdir -p "$WINEPREFIX"
bash run-wine.sh
```

Wine refuses to create a prefix directly under `/tmp` ("'/tmp' is not
owned by you") unless the folder exists already; `run-wine.sh` creates it
too.

Windows: copy `quotetest.msi` and `run-windows.cmd` into the VM, run the
.cmd as Administrator, bring back its four lines. (Its first version ran
C through `call :form`, where `=` outside quotes splits the arguments of a
batch label, so only `INSTALLDIR` arrived; C and D were run by hand in the
measurement above, and the script now runs every form directly.)
