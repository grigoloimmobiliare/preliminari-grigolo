@echo off
rem Rimuove Preliminari Grigolo da questo PC (le pratiche non vengono cancellate).
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0disinstalla.ps1"
