@echo off
rem Avvia il programma delle valutazioni su questo PC.
rem Il programma viene copiato (e aggiornato) dalla cartella condivisa sul PC, i dati restano sul server.
setlocal
title Valutazioni - Grigolo Immobiliare
set "CONDIVISA=%~dp0"
set "LOCALE=%LOCALAPPDATA%\Valutazioni Grigolo\Programma"

tasklist /FI "IMAGENAME eq Valutazioni.exe" 2>nul | find /I "Valutazioni.exe" >nul
if not errorlevel 1 goto avvia

echo Aggiornamento del programma su questo PC (la prima volta puo' richiedere un minuto)...
robocopy "%CONDIVISA%Programma" "%LOCALE%" /MIR /R:2 /W:2 /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
    echo.
    echo Non riesco a copiare il programma dalla cartella condivisa:
    echo   %CONDIVISA%Programma
    echo Controlla di essere collegato alla rete dell'ufficio.
    pause
    exit /b 1
)

:avvia
"%LOCALE%\Valutazioni.exe" "%CONDIVISA%Dati"
