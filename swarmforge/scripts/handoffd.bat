@echo off
rem Windows wrapper for handoffd.bb (babashka native). Enables invocation from
rem cmd/PowerShell and lets bb.exe spawn the helper on Windows.
setlocal
set "BB=bb"
where bb >nul 2>&1 || set "BB=bb.exe"
"%BB%" "%~dp0handoffd.bb" %*
