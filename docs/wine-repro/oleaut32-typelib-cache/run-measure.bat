@echo off
rem MEASURE oleaut32 typelib cache - run in the Windows VM, send back measure-result.txt
echo === measure64 > measure-result.txt
measure64.exe >> measure-result.txt 2>&1
echo === measure32 >> measure-result.txt
measure32.exe >> measure-result.txt 2>&1
echo === measure64 small (300 x 10) >> measure-result.txt
measure64.exe 300 10 20 >> measure-result.txt 2>&1
type measure-result.txt
