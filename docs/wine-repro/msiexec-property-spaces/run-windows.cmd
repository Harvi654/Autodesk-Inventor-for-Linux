@echo off
rem The msiexec quoting test on Windows 10 (as Administrator, quotetest.msi
rem next to this file): a property value with a space passed four ways.
rem A and B are the command lines Wine builds for one argument, C is ODIS's
rem form, D a control without a space. msiexec runs directly, not through
rem "call :label", which would split INSTALLDIR="..." at the "=" (the
rem first version of this script did); a batch file waits for msiexec.
rem Prints exit code and where marker.txt landed.
cd /d "%~dp0"
set "MSI=%~dp0quotetest.msi"

rem A: "INSTALLDIR=C:\quote test\a"    (one quoted argument)
msiexec /i "%MSI%" /qn "INSTALLDIR=C:\quote test\a"
call :check "A one quoted argument"

rem B: the same with a trailing backslash (doubled by Wine's command line)
msiexec /i "%MSI%" /qn "INSTALLDIR=C:\quote test\a\\"
call :check "B one quoted argument, trailing backslash"

rem C: INSTALLDIR="C:\quote test\a\"   (ODIS's form)
msiexec /i "%MSI%" /qn INSTALLDIR="C:\quote test\a\"
call :check "C value in quotes (ODIS form)"

rem D: INSTALLDIR=C:\quotetest   (no space, control)
msiexec /i "%MSI%" /qn INSTALLDIR=C:\quotetest
call :check "D no space (control)"
exit /b 0

:check
set rc=%errorlevel%
set where=nowhere
if exist "C:\quote test\a\marker.txt" set where=C:\quote test\a
if exist "C:\quotetest\marker.txt" set where=C:\quotetest
if exist "C:\Program Files (x86)\QuoteTest\marker.txt" set where=C:\Program Files (x86)\QuoteTest
echo %~1  exit %rc%  marker.txt in %where%
msiexec /x "%MSI%" /qn
rd /s /q "C:\quote test" 2>nul
rd /s /q "C:\quotetest" 2>nul
exit /b 0
