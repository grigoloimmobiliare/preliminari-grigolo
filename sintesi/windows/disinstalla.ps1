#Requires -Version 5.1
<#
  Rimuove "Sintesi immobili" da questo PC Windows.
  I documenti e i PDF di sintesi NON vengono cancellati.
#>
$ErrorActionPreference = 'Stop'

$principale = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principale.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit 0
}

$Radice = 'C:\SintesiGrigolo'
$NomeAttivita = 'Sintesi Immobili Grigolo'
$FileImpostazioni = Join-Path $Radice 'impostazioni.json'
$imp = if (Test-Path $FileImpostazioni) { Get-Content $FileImpostazioni -Raw -Encoding UTF8 | ConvertFrom-Json } else { $null }

Write-Host "Disinstallazione di Sintesi immobili" -ForegroundColor Cyan
if ($imp) { Write-Host "I documenti in $($imp.cartella_dati) NON verranno cancellati." }
$r = Read-Host "Procedere? [s/N]"
if (-not $r.Trim().ToLower().StartsWith('s')) { exit 0 }

if (Get-ScheduledTask -TaskName $NomeAttivita -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $NomeAttivita -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $NomeAttivita -Confirm:$false
}
Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object { $_.CommandLine -like '*avvia_sintesi.py*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-NetFirewallRule -DisplayName $NomeAttivita -ErrorAction SilentlyContinue | Remove-NetFirewallRule
Remove-Item (Join-Path $env:PUBLIC 'Desktop\Sintesi immobili.url') -ErrorAction SilentlyContinue
if ($imp -and $imp.condivisione -and (Get-SmbShare -Name $imp.condivisione -ErrorAction SilentlyContinue)) {
    Remove-SmbShare -Name $imp.condivisione -Force
}
Start-Sleep -Seconds 2
foreach ($c in @('programma', 'venv', 'log')) {
    Remove-Item (Join-Path $Radice $c) -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host ""
Write-Host "Programma rimosso." -ForegroundColor Green
if ($imp) { Write-Host "Documenti e PDF sono ancora in: $($imp.cartella_dati)" }
Read-Host "Premi Invio per chiudere"
