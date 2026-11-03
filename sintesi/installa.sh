#!/bin/bash
# Installa (o aggiorna) il programma "Sintesi immobili" sul NAS.
#
# Uso, collegati al NAS in SSH e dalla cartella del programma:
#     sudo ./sintesi/installa.sh
# Rilanciandolo in seguito aggiorna il programma mantenendo documenti e impostazioni.

set -euo pipefail
cd "$(dirname "$0")"

rosso() { printf '\033[31m%s\033[0m\n' "$*"; }
verde() { printf '\033[32m%s\033[0m\n' "$*"; }

if docker compose version >/dev/null 2>&1; then
    COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE=(docker-compose)
else
    rosso "Docker non trovato."
    echo "Synology: installa 'Container Manager' dal Centro pacchetti."
    echo "QNAP: installa 'Container Station' dall'App Center."
    exit 1
fi
if ! docker info >/dev/null 2>&1; then
    rosso "Non ho i permessi per usare Docker: rilancia con  sudo ./sintesi/installa.sh"
    exit 1
fi

if [ ! -f .env ]; then
    echo "Prima installazione: servono alcune impostazioni (Invio = valore proposto)."
    predefinita=/volume1/Sintesi
    [ -d /share ] && [ ! -d /volume1 ] && predefinita=/share/Sintesi
    read -rp "Cartella condivisa del NAS per documenti e PDF di sintesi [$predefinita]: " cartella
    cartella=${cartella:-$predefinita}
    read -rp "Porta della pagina web [8081]: " porta
    porta=${porta:-8081}
    utente=${SUDO_USER:-$(id -un)}
    puid=$(id -u "$utente" 2>/dev/null || echo 1026)
    pgid=$(id -g "$utente" 2>/dev/null || echo 100)
    read -rp "Utente proprietario dei file (UID) [$puid]: " x; puid=${x:-$puid}
    read -rp "Gruppo proprietario dei file (GID) [$pgid]: " x; pgid=${x:-$pgid}
    cat > .env <<FINE
CARTELLA_DATI=$cartella
PORTA=$porta
PUID=$puid
PGID=$pgid
AGENZIA=Grigolo Immobiliare
FINE
    verde "Impostazioni salvate nel file sintesi/.env"
fi

# shellcheck disable=SC1091
source .env
mkdir -p "$CARTELLA_DATI"
chown -R "$PUID:$PGID" "$CARTELLA_DATI" 2>/dev/null || true

if [ -d ../.git ] && command -v git >/dev/null 2>&1; then
    (cd .. && git pull --ff-only) || echo "Aggiornamento git non riuscito: proseguo con la versione presente."
fi

echo "Costruzione e avvio del programma (la prima volta puo' richiedere alcuni minuti)..."
"${COMPOSE[@]}" up -d --build

ip=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$ip" ] && ip=$(ip route get 1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}')
verde "Fatto. Apri dal browser di un PC dell'ufficio:  http://${ip:-<indirizzo-del-NAS>}:${PORTA}"
echo "Documenti e PDF di sintesi si trovano nella cartella condivisa: $CARTELLA_DATI"
