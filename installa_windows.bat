@echo off
rem Installa o aggiorna Preliminari Grigolo su questo PC Windows (doppio clic).
if not exist "%~dp0windows\installa.ps1" (
  echo.
  echo  ERRORE: file del programma non trovati.
  echo  Probabilmente lo ZIP non e' stato estratto: fai clic destro sul file ZIP,
  echo  scegli "Estrai tutto...", poi avvia questo file dalla cartella estratta.
  echo.
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\installa.ps1" %*
if errorlevel 1 (
  echo.
  echo  L'installazione non e' partita. Il registro e' in %PUBLIC%\installazione_*.log
  pause
)
