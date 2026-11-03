@echo off
rem Installa o aggiorna "Sintesi immobili" su questo PC Windows (doppio clic).
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0sintesi\windows\installa.ps1" %*
