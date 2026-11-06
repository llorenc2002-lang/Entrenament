$ErrorActionPreference = 'Stop'
$Project = Split-Path -Parent $MyInvocation.MyCommand.Path
$OutputFile = Join-Path $Project 'render-secrets.txt'
if (Test-Path -LiteralPath $OutputFile) {
    throw 'Ya existe render-secrets.txt. Guárdalo en un gestor de contraseñas o elimínalo antes de generar otros secretos.'
}
$Python = Join-Path $Project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    throw 'No encuentro el entorno Python del proyecto. Instala primero requirements.txt.'
}
$AppPassword = & $Python -c 'import secrets; print(secrets.token_urlsafe(36))'
if ($LASTEXITCODE -ne 0 -or -not $AppPassword) { throw 'No pude crear la contraseña.' }
$EncryptionKey = & $Python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
if ($LASTEXITCODE -ne 0 -or -not $EncryptionKey) { throw 'No pude crear la clave de cifrado.' }
$Content = @(
    'Copia estos valores en Render → servicio → Environment. No compartas este archivo.'
    "SERRA_APP_PASSWORD=$AppPassword"
    "SERRA_ENCRYPTION_KEY=$EncryptionKey"
)
[IO.File]::WriteAllLines($OutputFile, $Content, [Text.UTF8Encoding]::new($false))
Write-Host 'Secretos creados localmente en render-secrets.txt.' -ForegroundColor Green
Write-Host 'Añádelos en la configuración privada del servicio Render y guarda el archivo en tu gestor de contraseñas.'

