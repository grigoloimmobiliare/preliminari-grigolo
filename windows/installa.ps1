#Requires -Version 5.1
<#
  Installa (o aggiorna) il programma dei preliminari su un PC Windows dell'ufficio,
  che fa da server per gli altri PC della rete.

  Si avvia con doppio clic su "installa_windows.bat" (nella cartella principale del programma).
  Cosa fa:
    1. installa, se mancano, Python 3.12, Tesseract OCR (con la lingua italiana) e LibreOffice;
    2. copia il programma in C:\PreliminariGrigolo e ne installa le librerie;
    3. crea un'attivita' pianificata che avvia il programma all'accensione del PC;
    4. apre la porta nel firewall di Windows (solo reti private/dominio) e crea un collegamento sul desktop.
  Rilanciandolo aggiorna il programma mantenendo pratiche e impostazioni.
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

$Sorgente = Split-Path -Parent $PSScriptRoot
$Radice = 'C:\PreliminariGrigolo'
$Programma = Join-Path $Radice 'programma'
$Venv = Join-Path $Radice 'venv'
$FileImpostazioni = Join-Path $Radice 'impostazioni.json'
$NomeAttivita = 'Preliminari Grigolo'

Write-Host "Installazione di Preliminari Grigolo" -ForegroundColor Cyan
if (-not (Test-Path (Join-Path $Sorgente 'app\main.py'))) {
    Errore "File del programma non trovati in $Sorgente. Estrai tutto lo ZIP scaricato da GitHub e avvia installa_windows.bat dalla cartella estratta."
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
    Info "Cartella in cui salvare pratiche e modello Word."
    Info "Puo' essere una cartella del NAS (es. \\NAS\Preliminari) oppure una cartella di questo PC."
    $predefinita = if ($imp) { $imp.cartella_dati } else { Join-Path $Radice 'dati' }
    $cartella = PercorsoDiRete (Chiedi "Cartella dati" $predefinita)
    $porta = [int](Chiedi "Porta della pagina web" $(if ($imp) { "$($imp.porta)" } else { '8080' }))
    $conLibreOffice = ChiediSiNo "Installare LibreOffice (serve a calcolare il numero di pagine del contratto)?" $true
    $imp = [pscustomobject]@{
        cartella_dati   = $cartella
        porta           = $porta
        libreoffice     = $conLibreOffice
        tesseract       = ''
        soffice         = ''
        condivisione    = ''
        account         = ''
    }
}
$DiRete = $imp.cartella_dati.StartsWith('\\')

# ---------------------------------------------------------------- winget
Titolo "Componenti necessari"
$winget = Get-Command winget.exe -ErrorAction SilentlyContinue
function InstallaConWinget([string]$id, [string]$nome) {
    if (-not $winget) {
        Errore "Manca 'winget' (Programma di installazione app). Installalo da Microsoft Store cercando 'Programma di installazione app', oppure installa $nome a mano, poi rilancia."
    }
    Info "Installazione di $nome (puo' richiedere alcuni minuti)..."
    & winget.exe install --id $id --exact --silent --scope machine --accept-package-agreements --accept-source-agreements | Out-Null
    if ($LASTEXITCODE -ne 0) {
        # alcuni pacchetti non supportano --scope machine
        & winget.exe install --id $id --exact --silent --accept-package-agreements --accept-source-agreements | Out-Null
    }
}

# --- Python 3.12
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

# --- Tesseract OCR con lingua italiana
$tesseract = "$env:ProgramFiles\Tesseract-OCR\tesseract.exe"
if (-not (Test-Path $tesseract)) {
    InstallaConWinget 'UB-Mannheim.TesseractOCR' 'Tesseract OCR'
    if (-not (Test-Path $tesseract)) { Errore "Installazione di Tesseract non riuscita. Scaricalo da https://github.com/UB-Mannheim/tesseract/wiki e rilancia." }
}
$tessdata = Join-Path (Split-Path $tesseract) 'tessdata'
foreach ($lingua in @('ita', 'eng')) {
    $file = Join-Path $tessdata "$lingua.traineddata"
    if (-not (Test-Path $file)) {
        Info "Download della lingua '$lingua' per Tesseract..."
        try {
            Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/tesseract-ocr/tessdata_fast/raw/main/$lingua.traineddata" -OutFile $file
        } catch { Errore "Download di $lingua.traineddata non riuscito: $($_.Exception.Message)" }
    }
}
$imp.tesseract = $tesseract
Ok "Tesseract: $tesseract (lingua italiana presente)"

# --- LibreOffice (facoltativo)
$soffice = "$env:ProgramFiles\LibreOffice\program\soffice.exe"
if ($imp.libreoffice) {
    if (-not (Test-Path $soffice)) { InstallaConWinget 'TheDocumentFoundation.LibreOffice' 'LibreOffice' }
    if (Test-Path $soffice) {
        $imp.soffice = $soffice
        Ok "LibreOffice: $soffice"
    } else {
        Attenzione "LibreOffice non installato: il numero di pagine andra' scritto a mano nel Word."
        $imp.soffice = ''
    }
}
$fonts = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts' -ErrorAction SilentlyContinue
if (-not ($fonts.PSObject.Properties.Name -match 'Garamond')) {
    Attenzione "Il carattere Garamond non e' installato su questo PC (arriva con Microsoft Office): il conteggio delle pagine potrebbe essere approssimativo."
}

# ---------------------------------------------------------------- arresto versione precedente
Titolo "Installazione del programma"
$attivita = Get-ScheduledTask -TaskName $NomeAttivita -ErrorAction SilentlyContinue
if ($attivita) {
    Info "Arresto della versione in esecuzione..."
    Stop-ScheduledTask -TaskName $NomeAttivita -ErrorAction SilentlyContinue
}
Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object { $_.CommandLine -like '*avvia_server.py*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

# ---------------------------------------------------------------- copia dei file
$stessaCartella = (Resolve-Path $Sorgente).Path.TrimEnd('\') -ieq $Programma.TrimEnd('\')
if (-not $stessaCartella) {
    & robocopy.exe $Sorgente $Programma /MIR /XD .git dati tests __pycache__ .pytest_cache /XF .env /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { Errore "Copia dei file non riuscita (robocopy codice $LASTEXITCODE)." }
}
Get-ChildItem -Path $Programma -Recurse -File | Unblock-File
Ok "Programma copiato in $Programma"

# ---------------------------------------------------------------- librerie Python
if (-not (Test-Path "$Venv\Scripts\python.exe")) {
    Info "Creazione dell'ambiente Python..."
    & $python -m venv $Venv
    if ($LASTEXITCODE -ne 0) { Errore "Creazione dell'ambiente Python non riuscita." }
}
Info "Installazione delle librerie (la prima volta puo' richiedere qualche minuto)..."
& "$Venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check --upgrade pip | Out-Null
& "$Venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r (Join-Path $Programma 'requirements.txt')
if ($LASTEXITCODE -ne 0) { Errore "Installazione delle librerie non riuscita (controlla la connessione a internet)." }
Ok "Librerie installate"

# ---------------------------------------------------------------- cartella dati
Titolo "Cartella dati"
try {
    New-Item -ItemType Directory -Force -Path (Join-Path $imp.cartella_dati 'pratiche') | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $imp.cartella_dati 'modello') | Out-Null
    Ok $imp.cartella_dati
} catch {
    if ($DiRete) {
        Attenzione "Non riesco a scrivere in $($imp.cartella_dati) da questa finestra. Verra' riprovato dal programma con l'account indicato qui sotto."
    } else {
        Errore "Impossibile creare la cartella $($imp.cartella_dati): $($_.Exception.Message)"
    }
}

# condivisione in rete di una cartella locale, per copiare i documenti da altri PC
if (-not $DiRete -and ($primaInstallazione -or $Riconfigura)) {
    if (ChiediSiNo "Condividere la cartella dati in rete, cosi' gli altri PC possono aprire le pratiche?" $true) {
        $nomeCondivisione = 'Preliminari'
        # "Utenti autenticati", indicato col codice di sistema per funzionare con Windows in qualsiasi lingua
        $utenti = (New-Object Security.Principal.SecurityIdentifier 'S-1-5-11').Translate([Security.Principal.NTAccount]).Value
        if (-not (Get-SmbShare -Name $nomeCondivisione -ErrorAction SilentlyContinue)) {
            New-SmbShare -Name $nomeCondivisione -Path $imp.cartella_dati -ChangeAccess $utenti | Out-Null
        }
        & icacls.exe $imp.cartella_dati /grant '*S-1-5-11:(OI)(CI)M' | Out-Null
        $imp.condivisione = $nomeCondivisione
        Ok "Cartella condivisa come \\$env:COMPUTERNAME\$nomeCondivisione"
    }
}

# salva le impostazioni (senza password)
$imp | ConvertTo-Json | Set-Content -Path $FileImpostazioni -Encoding UTF8

# ---------------------------------------------------------------- avvio automatico
Titolo "Avvio automatico"
if (-not $attivita -or $Riconfigura) {
    $azione = New-ScheduledTaskAction -Execute "$Venv\Scripts\pythonw.exe" `
        -Argument "`"$Programma\windows\avvia_server.py`"" -WorkingDirectory $Programma
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $opzioni = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1)
    if ($DiRete) {
        # l'account di sistema non puo' accedere alle cartelle del NAS: serve un utente con accesso
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

# firewall: solo reti private e di dominio (mai reti pubbliche)
Get-NetFirewallRule -DisplayName $NomeAttivita -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $NomeAttivita -Direction Inbound -Action Allow -Protocol TCP `
    -LocalPort $imp.porta -Profile Domain, Private | Out-Null
Ok "Porta $($imp.porta) aperta nel firewall (solo rete dell'ufficio)."

if ($primaInstallazione -and (ChiediSiNo "Impedire la sospensione del PC quando e' collegato alla corrente (consigliato: deve restare raggiungibile)?" $true)) {
    & powercfg.exe /change standby-timeout-ac 0 | Out-Null
    Ok "Sospensione disattivata."
}

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

$collegamento = Join-Path $env:PUBLIC 'Desktop\Preliminari Grigolo.url'
Set-Content -Path $collegamento -Value "[InternetShortcut]`r`nURL=$indirizzo/`r`n" -Encoding ASCII

$ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
    Select-Object -ExpandProperty IPAddress
Write-Host ""
Write-Host "Installazione completata." -ForegroundColor Green
Write-Host "Su questo PC: $indirizzo (collegamento 'Preliminari Grigolo' sul desktop)"
Write-Host "Dagli altri PC dell'ufficio: http://$($env:COMPUTERNAME):$($imp.porta)"
foreach ($x in $ip) { Write-Host "                           oppure http://$($x):$($imp.porta)" }
Write-Host "Pratiche e modello Word: $($imp.cartella_dati)"
Write-Host "Questo PC deve restare acceso perche' gli altri possano usare il programma."
Start-Process $indirizzo
Fine 0
