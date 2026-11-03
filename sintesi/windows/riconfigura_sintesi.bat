@echo off
rem Cambia cartella dati, porta o account di "Sintesi immobili".
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installa.ps1" -Riconfigura
