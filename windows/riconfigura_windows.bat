@echo off
rem Cambia cartella dati, porta o account del programma gia' installato.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installa.ps1" -Riconfigura
