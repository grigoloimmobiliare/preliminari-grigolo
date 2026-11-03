@echo off
rem Rimuove "Sintesi immobili" da questo PC (documenti e PDF non vengono cancellati).
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0disinstalla.ps1"
