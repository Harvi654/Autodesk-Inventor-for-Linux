@echo off
rem The msiexec quoting test on Windows 10 (the maintainer's offline VM,
rem as Administrator, quotetest.msi next to this file). The command lines
rem are the ones Wine builds (A, B) and ODIS's form (C), typed as they
rem reach msiexec. Prints exit code and where marker.txt landed.
cd /d "%~dp0"
rem A: "INSTALLDIR=C:\quote test\a"    (Wine's command line for one argument)
call :form "A one quoted argument" "INSTALLDIR=C:\quote test\a"
rem B: "INSTALLDIR=C:\quote test\a\\"  (the same with a trailing backslash, doubled by Wine)
call :form "B one quoted argument, trailing backslash" "INSTALLDIR=C:\quote test\a\\"
rem C: INSTALLDIR="C:\quote test\a\"   (ODIS's form)
call :form "C ODIS form" INSTALLDIR="C:\quote test\a\"
exit /b 0
:form
start /wait "" msiexec /i "%~dp0quotetest.msi" /qn %2
set rc=%errorlevel%
set where=nowhere
if exist "C:\quote test\a\marker.txt" set where=C:\quote test\a
if exist "C:\Program Files (x86)\QuoteTest\marker.txt" set where=C:\Program Files (x86)\QuoteTest
echo %~1  exit %rc%  marker.txt in %where%
start /wait "" msiexec /x "%~dp0quotetest.msi" /qn
rd /s /q "C:\quote test" 2>nul
exit /b 0
