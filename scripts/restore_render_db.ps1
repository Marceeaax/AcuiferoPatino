param(
    [Parameter(Mandatory = $true)]
    [string]$DatabaseUrl,

    [Parameter(Mandatory = $true)]
    [string]$DumpPath
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $DumpPath)) {
    throw "No existe el archivo de dump: $DumpPath"
}

$extension = [System.IO.Path]::GetExtension($DumpPath).ToLowerInvariant()

if ($extension -eq ".dump") {
    $pgRestore = (Get-Command pg_restore -ErrorAction Stop).Source
    Write-Host "Restaurando dump custom hacia Render..." -ForegroundColor Cyan
    & $pgRestore `
        --no-owner `
        --no-privileges `
        --verbose `
        --dbname="$DatabaseUrl" `
        "$DumpPath"
}
elseif ($extension -eq ".sql") {
    $psql = (Get-Command psql -ErrorAction Stop).Source
    Write-Host "Restaurando dump SQL hacia Render..." -ForegroundColor Cyan
    & $psql "$DatabaseUrl" -v ON_ERROR_STOP=1 -f "$DumpPath"
}
else {
    throw "Formato no soportado. Usa .sql o .dump"
}

Write-Host "Restauración finalizada." -ForegroundColor Green
