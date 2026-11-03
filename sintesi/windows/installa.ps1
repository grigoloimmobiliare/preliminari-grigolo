#Requires -Version 5.1
<#
  Installa (o aggiorna) il programma "Sintesi immobili" su un PC Windows dell'ufficio,
  che fa da server per gli altri PC della rete. Puo' stare sullo stesso PC dei preliminari:
  usa una cartella, una porta (8081) e un'attivita' pianificata propri.

  Si avvia con doppio clic su "installa_sintesi_windows.bat" (nella cartella principale del programma).
  Cosa fa:
    1. installa, se mancano, Python 3.12 e Tesseract OCR (serve solo per eventuali PDF scansionati);
    2. copia il programma in C:\SintesiGrigolo e ne installa le librerie;
    3. crea un'attivita' pianificata che avvia il programma all'accensione del PC;
    4. apre la porta nel firewall di Windows (solo reti private/dominio) e crea un collegamento sul desktop.
  Rilanciandolo aggiorna il programma mantenendo documenti e impostazioni.
#>
param([switch]$Riconfigura)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Titolo([string]$t) { Write-Host ""; Write-Host "== $t ==" -ForegroundColor Cyan }
function Ok([string]$t) { Write-Host "   $t" -ForegroundColor Green }
function Info([string]$t) { Write-Host "   $t" }
function Attenzione([string]$t) { Write-Host "   ATTENZIONE: $t" -ForegroundColor Yellow }
function Fine([int]$codice) { Write-Host ""; Read-Host "Premi Invio per chiudere"; exit $codice }
function Errore([string]$t) { Write-Host ""; Write-Host "ERRORE: $t" -ForegroundColor Red; Fine 1 }
function Chiedi([string]$domanda, [string]$predefinito) {
    $r = Read-Host "$domanda [$predefinito]"
    if ([string]::IsNullOrWhiteSpace($r)) { return $predefinito }
    return $r.Trim()
}
function ChiediSiNo([string]$domanda, [bool]$predefinito = $true) {
    $p = if ($predefinito) { 'S/n' } else { 's/N' }
    $r = Read-Host "$domanda [$p]"
    if ([string]::IsNullOrWhiteSpace($r)) { return $predefinito }
    return $r.Trim().ToLower().StartsWith('s')
}

# ---------------------------------------------------------------- amministratore
$principale = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principale.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Servono i permessi di amministratore: confermare la richiesta di Windows."
    $argomenti = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    if ($Riconfigura) { $argomenti += ' -Riconfigura' }
    try { Start-Process powershell.exe -Verb RunAs -ArgumentList $argomenti } catch { Errore "Permessi di amministratore non concessi." }
    exit 0
}

# questo script e' in <programma>\sintesi\windows
$Sorgente = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Radice = 'C:\SintesiGrigolo'
$Programma = Join-Path $Radice 'programma'
$Venv = Join-Path $Radice 'venv'
$FileImpostazioni = Join-Path $Radice 'impostazioni.json'
$NomeAttivita = 'Sintesi Immobili Grigolo'

Write-Host "Installazione di Sintesi immobili" -ForegroundColor Cyan
if (-not (Test-Path (Join-Path $Sorgente 'sintesi\main.py'))) {
    Errore "File del programma non trovati in $Sorgente. Estrai tutto lo ZIP scaricato da GitHub e avvia installa_sintesi_windows.bat dalla cartella estratta."
}
New-Item -ItemType Directory -Force -Path $Radice | Out-Null

# ---------------------------------------------------------------- impostazioni
$imp = $null
$primaInstallazione = -not (Test-Path $FileImpostazioni)
if (-not $primaInstallazione) {
    $imp = Get-Content $FileImpostazioni -Raw -Encoding UTF8 | ConvertFrom-Json
}

function PercorsoDiRete([string]$percorso) {
    # le unita' di rete (es. Z:) non sono visibili al programma avviato all'accensione:
    # vanno convertite nel percorso completo \\server\cartella
    if ($percorso -match '^([A-Za-z]):(.*)$') {
        $lettera = $Matches[1].ToUpper()
        $resto = $Matches[2]
        $remoto = $null
        $chiave = "HKCU:\Network\$lettera"
        if (Test-Path $chiave) { $remoto = (Get-ItemProperty $chiave).RemotePath }
        if (-not $remoto) {
            $unita = Get-PSDrive -Name $lettera -ErrorAction SilentlyContinue
            if ($unita -and $unita.DisplayRoot -like '\\*') { $remoto = $unita.DisplayRoot }
        }
        if ($remoto) { return ($remoto.TrimEnd('\') + $resto) }
    }
    return $percorso
}

if ($primaInstallazione -or $Riconfigura) {
    Titolo "Impostazioni"
    Info "Cartella in cui salvare documenti e PDF di sintesi."
    Info "Consigliata una cartella condivisa del NAS (es. \\NAS\Sintesi): chi copia li' i PDF ottiene la sintesi in automatico."
    $predefinita = if ($imp) { $imp.cartella_dati } else { Join-Path $Radice 'dati' }
    $cartella = PercorsoDiRete (Chiedi "Cartella dati" $predefinita)
    $porta = [int](Chiedi "Porta della pagina web (i preliminari usano la 8080)" $(if ($imp) { "$($imp.porta)" } else { '8081' }))
    $agenzia = Chiedi "Nome nell'intestazione del PDF" $(if ($imp -and $imp.agenzia) { $imp.agenzia } else { 'Grigolo Immobiliare' })
    $imp = [pscustomobject]@{
        cartella_dati   = $cartella
        porta           = $porta
        agenzia         = $agenzia
        tesseract       = ''
        condivisione    = ''
        account         = ''
    }
}
$DiRete = $imp.cartella_dati.StartsWith('\\')

# ---------------------------------------------------------------- componenti
Titolo "Componenti necessari"
$winget = Get-Command winget.exe -ErrorAction SilentlyContinue
function InstallaConWinget([string]$id, [string]$nome) {
    if (-not $winget) {
        Errore "Manca 'winget' (Programma di installazione app). Installalo da Microsoft Store cercando 'Programma di installazione app', oppure installa $nome a mano, poi rilancia."
    }
    Info "Installazione di $nome (puo' richiedere alcuni minuti)..."
    & winget.exe install --id $id --exact --silent --scope machine --accept-package-agreements --accept-source-agreements | Out-Null
    if ($LASTEXITCODE -ne 0) {
        & winget.exe install --id $id --exact --silent --accept-package-agreements --accept-source-agreements | Out-Null
    }
}

function TrovaPython {
    foreach ($p in @("$env:ProgramFiles\Python312\python.exe", "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe")) {
        if (Test-Path $p) { return $p }
    }
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        $r = & py.exe -3.12 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $r) { return "$r".Trim() }
    }
    return $null
}
$python = TrovaPython
if (-not $python) {
    InstallaConWinget 'Python.Python.3.12' 'Python 3.12'
    $python = TrovaPython
    if (-not $python) { Errore "Installazione di Python non riuscita. Installa Python 3.12 da https://www.python.org/downloads/windows/ e rilancia." }
}
Ok "Python: $python"

# Tesseract: serve solo per i PDF scansionati, quindi non blocca l'installazione
$tesseract = "$env:ProgramFiles\Tesseract-OCR\tesseract.exe"
if (-not (Test-Path $tesseract)) {
    try { InstallaConWinget 'UB-Mannheim.TesseractOCR' 'Tesseract OCR' } catch { }
}
if (Test-Path $tesseract) {
    $file = Join-Path (Join-Path (Split-Path $tesseract) 'tessdata') 'ita.traineddata'
    if (-not (Test-Path $file)) {
        try {
            Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/tesseract-ocr/tessdata_fast/raw/main/ita.traineddata" -OutFile $file
        } catch { Attenzione "Download della lingua italiana per Tesseract non riuscito." }
    }
    $imp.tesseract = $tesseract
    Ok "Tesseract: $tesseract"
} else {
    Attenzione "Tesseract non installato: i PDF digitali funzionano, quelli scansionati non potranno essere letti."
}

# ---------------------------------------------------------------- arresto versione precedente
Titolo "Installazione del programma"
$attivita = Get-ScheduledTask -TaskName $NomeAttivita -ErrorAction SilentlyContinue
if ($attivita) {
    Info "Arresto della versione in esecuzione..."
    Stop-ScheduledTask -TaskName $NomeAttivita -ErrorAction SilentlyContinue
}
Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object { $_.CommandLine -like '*avvia_sintesi.py*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

# ---------------------------------------------------------------- copia dei file
$stessaCartella = (Resolve-Path $Sorgente).Path.TrimEnd('\') -ieq $Programma.TrimEnd('\')
if (-not $stessaCartella) {
    & robocopy.exe $Sorgente $Programma /MIR /XD .git dati dati_sintesi tests __pycache__ .pytest_cache /XF .env /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { Errore "Copia dei file non riuscita (robocopy codice $LASTEXITCODE)." }
}
Get-ChildItem -Path $Programma -Recurse -File | Unblock-File
Ok "Programma copiato in $Programma"

if (-not (Test-Path "$Venv\Scripts\python.exe")) {
    Info "Creazione dell'ambiente Python..."
    & $python -m venv $Venv
    if ($LASTEXITCODE -ne 0) { Errore "Creazione dell'ambiente Python non riuscita." }
}
Info "Installazione delle librerie (la prima volta puo' richiedere qualche minuto)..."
& "$Venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check --upgrade pip | Out-Null
& "$Venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r (Join-Path $Programma 'sintesi\requirements.txt')
if ($LASTEXITCODE -ne 0) { Errore "Installazione delle librerie non riuscita (controlla la connessione a internet)." }
Ok "Librerie installate"

# ---------------------------------------------------------------- cartella dati
Titolo "Cartella dati"
try {
    New-Item -ItemType Directory -Force -Path $imp.cartella_dati | Out-Null
    Ok $imp.cartella_dati
} catch {
    if ($DiRete) {
        Attenzione "Non riesco a scrivere in $($imp.cartella_dati) da questa finestra. Verra' riprovato dal programma con l'account indicato qui sotto."
    } else {
        Errore "Impossibile creare la cartella $($imp.cartella_dati): $($_.Exception.Message)"
    }
}

if (-not $DiRete -and ($primaInstallazione -or $Riconfigura)) {
    if (ChiediSiNo "Condividere la cartella dati in rete, cosi' gli altri PC possono aprire i PDF?" $true) {
        $nomeCondivisione = 'Sintesi'
        $utenti = (New-Object Security.Principal.SecurityIdentifier 'S-1-5-11').Translate([Security.Principal.NTAccount]).Value
        if (-not (Get-SmbShare -Name $nomeCondivisione -ErrorAction SilentlyContinue)) {
            New-SmbShare -Name $nomeCondivisione -Path $imp.cartella_dati -ChangeAccess $utenti | Out-Null
        }
        & icacls.exe $imp.cartella_dati /grant '*S-1-5-11:(OI)(CI)M' | Out-Null
        $imp.condivisione = $nomeCondivisione
        Ok "Cartella condivisa come \\$env:COMPUTERNAME\$nomeCondivisione"
    }
}

$imp | ConvertTo-Json | Set-Content -Path $FileImpostazioni -Encoding UTF8

# ---------------------------------------------------------------- avvio automatico
Titolo "Avvio automatico"
if (-not $attivita -or $Riconfigura) {
    $azione = New-ScheduledTaskAction -Execute "$Venv\Scripts\pythonw.exe" `
        -Argument "`"$Programma\sintesi\windows\avvia_sintesi.py`"" -WorkingDirectory $Programma
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $opzioni = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1)
    if ($DiRete) {
        Info "La cartella dati e' sul NAS: il programma deve girare con un account Windows che vi ha accesso."
        Info "Indica utente e password (la password e' conservata solo da Windows, non dal programma)."
        $credenziali = Get-Credential -Message "Account Windows con accesso a $($imp.cartella_dati)" -UserName "$env:USERDOMAIN\$env:USERNAME"
        if (-not $credenziali) { Errore "Credenziali non inserite." }
        Register-ScheduledTask -TaskName $NomeAttivita -Action $azione -Trigger $trigger -Settings $opzioni `
            -User $credenziali.UserName -Password $credenziali.GetNetworkCredential().Password -RunLevel Highest -Force | Out-Null
        $imp.account = $credenziali.UserName
        $imp | ConvertTo-Json | Set-Content -Path $FileImpostazioni -Encoding UTF8
    } else {
        $sistema = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
        Register-ScheduledTask -TaskName $NomeAttivita -Action $azione -Trigger $trigger -Settings $opzioni `
            -Principal $sistema -Force | Out-Null
    }
    Ok "Attivita' pianificata '$NomeAttivita' creata: il programma parte all'accensione del PC."
} else {
    Ok "Attivita' pianificata gia' presente."
}

Get-NetFirewallRule -DisplayName $NomeAttivita -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $NomeAttivita -Direction Inbound -Action Allow -Protocol TCP `
    -LocalPort $imp.porta -Profile Domain, Private | Out-Null
Ok "Porta $($imp.porta) aperta nel firewall (solo rete dell'ufficio)."

# ---------------------------------------------------------------- avvio e verifica
Titolo "Avvio"
Start-ScheduledTask -TaskName $NomeAttivita
$indirizzo = "http://localhost:$($imp.porta)"
$avviato = $false
for ($i = 0; $i -lt 45; $i++) {
    Start-Sleep -Seconds 2
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri "$indirizzo/salute" -TimeoutSec 3
        if ($r.StatusCode -eq 200) { $avviato = $true; break }
    } catch { }
}
if (-not $avviato) {
    $log = Join-Path $Radice 'log\server.log'
    Write-Host ""
    Write-Host "Il programma non risponde. Ultime righe del log ($log):" -ForegroundColor Red
    if (Test-Path $log) { Get-Content $log -Tail 25 }
    Fine 1
}

$collegamento = Join-Path $env:PUBLIC 'Desktop\Sintesi immobili.url'
Set-Content -Path $collegamento -Value "[InternetShortcut]`r`nURL=$indirizzo/`r`n" -Encoding ASCII

$ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
    Select-Object -ExpandProperty IPAddress
Write-Host ""
Write-Host "Installazione completata." -ForegroundColor Green
Write-Host "Su questo PC: $indirizzo (collegamento 'Sintesi immobili' sul desktop)"
Write-Host "Dagli altri PC dell'ufficio: http://$($env:COMPUTERNAME):$($imp.porta)"
foreach ($x in $ip) { Write-Host "                           oppure http://$($x):$($imp.porta)" }
Write-Host "Documenti e PDF di sintesi: $($imp.cartella_dati)"
Write-Host "Questo PC deve restare acceso perche' gli altri possano usare il programma."
Start-Process $indirizzo
Fine 0
