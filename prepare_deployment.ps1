$ErrorActionPreference = 'Stop'
$Project = Split-Path -Parent $MyInvocation.MyCommand.Path
$Domain = Read-Host 'Dominio público que apuntará a tu servidor (por ejemplo, entreno.tudominio.es)'
if ($Domain -notmatch '^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$') { throw 'El dominio no tiene un formato válido.' }
$Python = Join-Path $Project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) { throw 'No encuentro .venv. Instala primero requirements.txt.' }
$Rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$RandomBytes = New-Object byte[] 48
$Rng.GetBytes($RandomBytes)
$SessionSecret = [Convert]::ToBase64String($RandomBytes).TrimEnd('=').Replace('+','-').Replace('/','_')
$PasswordBytes = New-Object byte[] 36
$Rng.GetBytes($PasswordBytes)
$Rng.Dispose()
$AppPassword = [Convert]::ToBase64String($PasswordBytes).TrimEnd('=').Replace('+','-').Replace('/','_')
$EncryptionKey = & $Python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
if ($LASTEXITCODE -ne 0 -or -not $EncryptionKey) { throw 'No pude generar la clave de cifrado.' }
$EnvFile = Join-Path $Project '.env'
$Content = @(
  "SERRA_DOMAIN=$Domain"
  "SERRA_APP_PASSWORD=$AppPassword"
  "SERRA_SESSION_SECRET=$SessionSecret"
  "SERRA_ENCRYPTION_KEY=$EncryptionKey"
)
[IO.File]::WriteAllLines($EnvFile, $Content, [Text.UTF8Encoding]::new($false))
Write-Host ''
Write-Host 'Configuración creada en .env (archivo privado, excluido de Git).' -ForegroundColor Green
Write-Host 'Contraseña de acceso de la app (guárdala en un gestor de contraseñas):' -ForegroundColor Yellow
Write-Host $AppPassword
Write-Host 'Transfiere .env al servidor solo por SSH/SFTP y no lo envíes por correo ni chat.'

