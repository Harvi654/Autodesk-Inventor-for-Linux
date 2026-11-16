# msiexec: a property value with a space, passed as one argument

Found 2026-11-16 by the installer completeness review: Inventor 2027's
`InvPrivate.msi` with `INSTALLDIR=C:\Program Files\Autodesk\Inventor 2027\`
ended at once with exit code 103 (= 1639, `ERROR_INVALID_COMMAND_LINE`).
Revit's earlier "MSI property values with a space fail" is the same.

## What happens in Wine (read in Wine 11.20's source)

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

## What Windows does - to be measured

Not yet measured (AGENTS.md: expected values come from Windows, not from
reading). `run-windows.cmd` passes forms A, B (what Wine builds) and C
(ODIS's form) to Windows' msiexec; `run-wine.sh` the same under Wine plus
a control without a space. The MSI is synthetic (`quotetest.wxs`, built
with msitools' `wixl`), so the test can go into a bug report.

```bash
cd docs/wine-repro/msiexec-property-spaces
echo marker > marker.txt
wixl quotetest.wxs
export WINEPREFIX=/tmp/quotetest-prefix
bash run-wine.sh
```

Windows: copy `quotetest.msi` and `run-windows.cmd` into the VM, run the
.cmd as Administrator, bring back its three lines.

## Results

| Form | Wine 11.20 (winum-11.20-2) | Windows 10 |
|---|---|---|
| A `"INSTALLDIR=C:\quote test\a"` | expected 1639 (from the source), not run yet | not measured |
| B `"INSTALLDIR=C:\quote test\a\\"` | expected 1639, not run yet | not measured |
| C `INSTALLDIR="C:\quote test\a\"` (batch file) | expected: installs to `C:\quote test\a` | not measured |
| D no space (control) | expected: installs | - |

## For a bug report on bugs.winehq.org

In words, once Windows is measured: the program's arguments, the command
line Wine builds (step 2), what Wine's msiexec makes of it (steps 3-5,
exit code 1639), what Windows' msiexec does with the same command line,
and this synthetic MSI with the two scripts. Not filed yet.
