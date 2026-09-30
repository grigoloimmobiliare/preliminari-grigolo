@echo off
rem Installa o aggiorna Preliminari Grigolo su questo PC Windows (doppio clic).
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\installa.ps1" %*
