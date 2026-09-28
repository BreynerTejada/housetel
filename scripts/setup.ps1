# Crea el archivo .env a partir de .env.example con claves nuevas (DJANGO_SECRET_KEY y FERNET_KEY).
# Es seguro correrlo varias veces: si .env ya existe, no lo toca.
# Uso (Windows PowerShell, desde la carpeta del proyecto):
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

if (Test-Path '.env') {
    Write-Host '.env ya existe: no se modifica.'
    exit 0
}

function New-RandomBase64Url([int]$ByteCount) {
    $buffer = New-Object byte[] $ByteCount
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buffer)
    return [Convert]::ToBase64String($buffer).Replace('+', '-').Replace('/', '_')
}

$secret = (New-RandomBase64Url 48).TrimEnd('=')
$fernet = New-RandomBase64Url 32   # 44 caracteres con '=' final: formato que exige Fernet

$lines = Get-Content '.env.example' -Encoding UTF8 | ForEach-Object {
    if ($_ -eq 'DJANGO_SECRET_KEY=') { "DJANGO_SECRET_KEY=$secret" }
    elseif ($_ -eq 'FERNET_KEY=') { "FERNET_KEY=$fernet" }
    else { $_ }
}

# UTF-8 sin BOM y saltos de línea LF: Docker lee este archivo desde Linux.
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$target = Join-Path (Get-Location) '.env'
[System.IO.File]::WriteAllText($target, (($lines -join "`n") + "`n"), $utf8NoBom)

Write-Host '.env creado con claves nuevas.'
Write-Host 'Siguiente paso: docker compose up -d --build'
