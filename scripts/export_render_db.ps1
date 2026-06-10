param(
    [string]$DbName = "tesisdb",
    [string]$DbUser = "postgres",
    [string]$DbHost = "localhost",
    [string]$DbPort = "5432",
    [string]$OutputDir = "backups",
    [ValidateSet("plain", "custom")]
    [string]$Format = "plain"
)

$ErrorActionPreference = "Stop"

$pgDump = (Get-Command pg_dump -ErrorAction Stop).Source
$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

$extension = if ($Format -eq "custom") { "dump" } else { "sql" }
$outputPath = Join-Path $OutputDir "${DbName}_render_${timestamp}.${extension}"

$args = @(
    "--host=$DbHost",
    "--port=$DbPort",
    "--username=$DbUser",
    "--dbname=$DbName",
    "--no-owner",
    "--no-privileges",
    "--verbose"
)

if ($Format -eq "custom") {
    $args += @("--format=custom", "--file=$outputPath")
} else {
    $args += @("--format=plain", "--file=$outputPath")
}

Write-Host "Exportando base '$DbName' a $outputPath ..." -ForegroundColor Cyan
& $pgDump @args

Write-Host "Dump generado en: $outputPath" -ForegroundColor Green
