#!/bin/bash
# Installa o aggiorna il programma Preliminari Grigolo su un NAS SENZA accesso a internet.
#
# Il pacchetto contiene il programma già pronto (immagini Docker per processori Intel/AMD e ARM).
# 1. Estrai lo ZIP del pacchetto su un PC e copia la cartella in una cartella condivisa del NAS,
#    ad esempio \\NAS\Preliminari\installazione
# 2. Collegati al NAS in SSH ed esegui (adatta il percorso):
#        sudo bash /volume1/Preliminari/installazione/installa_offline.sh
#
# Per aggiornare: copia il pacchetto nuovo e rilancia lo stesso comando. Le impostazioni (cartella
# dei dati, porta, utente) vengono riprese dal programma già installato; pratiche, modello Word,
# stanno nella cartella dei dati e non vengono toccati.

set -euo pipefail

NOME=preliminari-grigolo
IMMAGINE=preliminari-grigolo:latest
QUI="$(cd "$(dirname "$0")" && pwd)"

# Su Synology docker sta in /usr/local/bin, che con sudo può mancare dal PATH.
export PATH="$PATH:/usr/local/bin:/usr/local/sbin:/usr/syno/bin"

rosso() { printf '\033[31m%s\033[0m\n' "$*"; }
verde() { printf '\033[32m%s\033[0m\n' "$*"; }
chiedi() {  # chiedi "domanda" valore_proposto -> stampa la risposta
    local r=""
    read -rp "$1 [$2]: " r || true
    echo "${r:-$2}"
}

# Le domande vanno lette dalla tastiera anche se lo script è stato avviato in altro modo.
if [ ! -t 0 ] && { : < /dev/tty; } 2>/dev/null; then
    exec < /dev/tty
fi

if [ "$(id -u)" -ne 0 ]; then
    rosso "Serve l'amministratore: rilancia con  sudo bash $0"
    exit 1
fi

# --- Docker
if ! command -v docker >/dev/null 2>&1; then
    rosso "Docker non è installato sul NAS."
    echo "Va installato prima, senza internet, dal pacchetto scaricato su un PC (vedi LEGGIMI.txt):"
    echo "  Synology: Container Manager (DSM 7.2 o successivo) oppure Docker (DSM 6 / 7.0 / 7.1)"
    echo "  QNAP: Container Station"
    echo "Poi rilancia questo script."
    exit 1
fi
if ! docker info >/dev/null 2>&1; then
    rosso "Docker è installato ma non risponde. Avvia Container Manager / Container Station e riprova."
    exit 1
fi

# --- processore del NAS
case "$(uname -m)" in
    x86_64|amd64) arch=amd64; desc="Intel/AMD" ;;
    aarch64|arm64) arch=arm64; desc="ARM 64 bit" ;;
    *)
        rosso "Il processore di questo NAS ($(uname -m)) non è supportato: servono Intel/AMD o ARM 64 bit."
        exit 1 ;;
esac
file_immagine=""
for f in "$QUI/immagini/immagine-$arch.tar.gz" "$QUI/immagine-$arch.tar.gz" \
         "$QUI/immagini/immagine-$arch.tar" "$QUI/immagine-$arch.tar"; do
    [ -f "$f" ] && file_immagine="$f" && break
done
if [ -z "$file_immagine" ]; then
    rosso "Nel pacchetto manca il file immagini/immagine-$arch.tar.gz (processore $desc)."
    echo "Scarica il pacchetto completo e copia tutta la cartella sul NAS."
    exit 1
fi
echo "Processore del NAS: $desc."

# --- impostazioni: dal programma già installato, altrimenti si chiedono
cartella="" porta="" utente=""
if docker inspect --type container "$NOME" >/dev/null 2>&1; then
    cartella=$(docker inspect --type container -f '{{range .Mounts}}{{if eq .Destination "/dati"}}{{.Source}}{{end}}{{end}}' "$NOME" || true)
    porta=$(docker inspect --type container -f '{{range $p, $b := .HostConfig.PortBindings}}{{if eq $p "8080/tcp"}}{{(index $b 0).HostPort}}{{end}}{{end}}' "$NOME" || true)
    utente=$(docker inspect --type container -f '{{.Config.User}}' "$NOME" || true)
    echo "Aggiornamento: riprendo le impostazioni del programma installato."
fi
if [ -z "$cartella" ] || [ -z "$porta" ]; then
    echo "Prima installazione: servono alcune impostazioni (Invio = valore proposto)."
    predefinita=/volume1/Preliminari
    [ -d /share ] && [ ! -d /volume1 ] && predefinita=/share/Preliminari
    cartella=$(chiedi "Cartella condivisa del NAS per i dati del programma" "$predefinita")
    porta=$(chiedi "Porta della pagina web" 8080)
    chi=${SUDO_USER:-$(id -un)}
    puid=$(chiedi "Utente proprietario dei file (UID)" "$(id -u "$chi" 2>/dev/null || echo 1026)")
    pgid=$(chiedi "Gruppo proprietario dei file (GID)" "$(id -g "$chi" 2>/dev/null || echo 100)")
    utente="$puid:$pgid"
fi
[ -z "$utente" ] && utente="1026:100"

if [ ! -d "$cartella" ]; then
    rosso "La cartella $cartella non esiste."
    echo "Creala come cartella condivisa dal pannello del NAS (es. 'Preliminari') e rilancia lo script."
    exit 1
fi
mkdir -p "$cartella/pratiche" "$cartella/modello"
chown -R "$utente" "$cartella/pratiche" "$cartella/modello" 2>/dev/null || true

# --- caricamento del programma e avvio
echo "Carico il programma in Docker (qualche minuto)..."
docker load -i "$file_immagine"

if docker inspect --type container "$NOME" >/dev/null 2>&1; then
    echo "Fermo la versione precedente..."
    docker rm -f "$NOME" >/dev/null
fi
docker run -d --name "$NOME" --restart unless-stopped \
    -p "$porta:8080" -v "$cartella:/dati" --user "$utente" -e TZ=Europe/Rome \
    "$IMMAGINE" >/dev/null
docker image prune -f >/dev/null 2>&1 || true   # toglie le versioni vecchie non più usate

echo "Avvio in corso..."
pronto=""
for _ in $(seq 1 60); do
    if docker exec "$NOME" python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/salute')" \
        >/dev/null 2>&1; then
        pronto=1
        break
    fi
    sleep 2
done
if [ -z "$pronto" ]; then
    rosso "Il programma non risponde. Ultime righe del registro:"
    docker logs --tail 30 "$NOME" || true
    exit 1
fi

ip=$(hostname -I 2>/dev/null | awk '{print $1}' || true)
[ -z "$ip" ] && ip=$(ip route get 1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}' || true)
verde "Fatto. Apri dal browser di un PC dell'ufficio:  http://${ip:-<indirizzo-del-NAS>}:${porta}"
echo "Nella cartella $cartella trovi pratiche/ e modello/."
echo "Il programma riparte da solo anche dopo un riavvio del NAS."
echo "Questa cartella di installazione ora si può cancellare."
