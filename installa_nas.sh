#!/bin/bash
# Installa o aggiorna il programma Preliminari Grigolo sul NAS, scaricandolo da GitHub.
#
# Collegati al NAS in SSH e incolla questo comando (una sola riga):
#
#   sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/grigoloimmobiliare/preliminari-grigolo/HEAD/installa_nas.sh)"
#
# Oppure copia questo file sul NAS ed esegui:  sudo bash installa_nas.sh
#
# Cosa fa:
#   1. scarica l'ultima versione del programma da GitHub (non serve git);
#   2. la mette nella cartella del programma (es. /volume1/docker/preliminari-grigolo),
#      lasciando invariate le impostazioni (.env);
#   3. lancia installa.sh, che costruisce e avvia il programma con Docker.
# Pratiche e modello Word stanno nella cartella condivisa dei
# dati e non vengono toccati. Rilancialo ogni volta che vuoi aggiornare il programma.
#
# Variabili facoltative: CARTELLA_PROGRAMMA (dove installare), RAMO (ramo di GitHub da scaricare).

set -euo pipefail

REPO="grigoloimmobiliare/preliminari-grigolo"
RAMO="${RAMO:-HEAD}"   # HEAD = ramo principale del repository

rosso() { printf '\033[31m%s\033[0m\n' "$*"; }
verde() { printf '\033[32m%s\033[0m\n' "$*"; }

# Le domande vanno lette dalla tastiera anche quando lo script arriva da curl.
if [ ! -t 0 ] && { : < /dev/tty; } 2>/dev/null; then
    exec < /dev/tty
fi

if [ "$(id -u)" -ne 0 ]; then
    rosso "Serve l'amministratore: rilancia mettendo  sudo  davanti al comando."
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    rosso "Docker non trovato."
    echo "Synology: installa 'Container Manager' dal Centro pacchetti."
    echo "QNAP: installa 'Container Station' dall'App Center."
    exit 1
fi

# --- cartella del programma
if [ -z "${CARTELLA_PROGRAMMA:-}" ]; then
    if [ -d /volume1 ]; then
        predefinita=/volume1/docker/preliminari-grigolo          # Synology
    elif [ -d /share/Container ]; then
        predefinita=/share/Container/preliminari-grigolo         # QNAP
    else
        predefinita=/opt/preliminari-grigolo
    fi
    read -rp "Cartella in cui installare il programma [$predefinita]: " CARTELLA_PROGRAMMA || true
    CARTELLA_PROGRAMMA=${CARTELLA_PROGRAMMA:-$predefinita}
fi
mkdir -p "$CARTELLA_PROGRAMMA"

# --- scaricamento
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
url="https://github.com/$REPO/archive/$RAMO.tar.gz"
echo "Scarico il programma da GitHub..."
if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" -o "$tmp/programma.tar.gz"
elif command -v wget >/dev/null 2>&1; then
    wget -q "$url" -O "$tmp/programma.tar.gz"
else
    rosso "Servono curl o wget per scaricare il programma."
    exit 1
fi
mkdir "$tmp/estratto"
tar -xzf "$tmp/programma.tar.gz" -C "$tmp/estratto"
sorgente=$(find "$tmp/estratto" -mindepth 1 -maxdepth 1 -type d | head -n 1)
if [ ! -f "$sorgente/installa.sh" ] || [ ! -f "$sorgente/docker-compose.yml" ]; then
    rosso "Il file scaricato non contiene il programma. Controlla la connessione e riprova."
    exit 1
fi

# --- sostituzione del programma (le impostazioni .env restano)
if [ -f "$CARTELLA_PROGRAMMA/.env" ]; then
    cp -p "$CARTELLA_PROGRAMMA/.env" "$tmp/env"
    echo "Aggiornamento: mantengo le impostazioni esistenti."
fi
find "$CARTELLA_PROGRAMMA" -mindepth 1 -maxdepth 1 ! -name .env ! -name dati -exec rm -rf {} +
cp -a "$sorgente/." "$CARTELLA_PROGRAMMA/"
[ -f "$tmp/env" ] && cp -p "$tmp/env" "$CARTELLA_PROGRAMMA/.env"
chmod +x "$CARTELLA_PROGRAMMA/installa.sh"
verde "Programma copiato in $CARTELLA_PROGRAMMA"

# --- installazione con Docker
cd "$CARTELLA_PROGRAMMA"
exec bash ./installa.sh
