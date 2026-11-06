$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$Cloudflared = Join-Path $ProjectRoot 'tools\cloudflared-windows-amd64.exe'
$LocalState = Join-Path $env:LOCALAPPDATA 'LoloTrainingApp'
$RuntimeLogs = Join-Path $LocalState 'logs'
$TunnelOut = Join-Path $RuntimeLogs 'cloudflared.out.log'
$TunnelErr = Join-Path $RuntimeLogs 'cloudflared.err.log'
$ServerOut = Join-Path $RuntimeLogs 'server.out.log'
$ServerErr = Join-Path $RuntimeLogs 'server.err.log'
$ServerProcess = $null
$TunnelProcess = $null

function New-RandomHex([int] $ByteCount) {
    $bytes = New-Object byte[] $ByteCount
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return ([BitConverter]::ToString($bytes) -replace '-', '').ToLowerInvariant()
}

function New-AppPassword {
    $alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'
    $result = [System.Text.StringBuilder]::new()
    $bytes = New-Object byte[] 4
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    for ($i = 0; $i -lt 36; $i++) {
        $rng.GetBytes($bytes)
        $index = [BitConverter]::ToUInt32($bytes, 0) % $alphabet.Length
        [void]$result.Append($alphabet[[int]$index])
    }
    $rng.Dispose()
    return $result.ToString()
}

function Save-ProtectedValue([string] $Name, [string] $Value) {
    $secure = ConvertTo-SecureString -String $Value -AsPlainText -Force
    $encrypted = ConvertFrom-SecureString -SecureString $secure
    Set-Content -LiteralPath (Join-Path $LocalState "$Name.dpapi") -Value $encrypted -NoNewline
}

function Read-ProtectedValue([string] $Name) {
    $path = Join-Path $LocalState "$Name.dpapi"
    $encrypted = Get-Content -LiteralPath $path -Raw
    $secure = ConvertTo-SecureString -String $encrypted
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

try {
    if (-not (Test-Path -LiteralPath $Python)) {
        throw 'Falta el entorno Python del proyecto. Abre README_LOCAL_APP.md y completa la instalación.'
    }
    if (-not (Test-Path -LiteralPath $LocalState)) {
        New-Item -ItemType Directory -Path $LocalState -Force | Out-Null
    }
    New-Item -ItemType Directory -Path $RuntimeLogs -Force | Out-Null

    $newPassword = $false
    $passwordPath = Join-Path $LocalState 'app-password.dpapi'
    if (-not (Test-Path -LiteralPath $passwordPath)) {
        $password = New-AppPassword
        Save-ProtectedValue 'app-password' $password
        $newPassword = $true
        Write-Host 'Contraseña privada de la app (guárdala; solo se muestra esta vez):' -ForegroundColor Yellow
        Write-Host $password -ForegroundColor Yellow
    } else { $password = Read-ProtectedValue 'app-password' }

    if (-not (Test-Path -LiteralPath (Join-Path $LocalState 'session-secret.dpapi'))) {
        Save-ProtectedValue 'session-secret' (New-RandomHex 48)
    }
    $dataDir = Join-Path $ProjectRoot 'data\app'
    New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
    $encryptionKeyFile = Join-Path $dataDir 'local_encryption.key'
    if (-not (Test-Path -LiteralPath $encryptionKeyFile)) {
        $newKey = (& $Python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode("ascii"))').Trim()
        if ($LASTEXITCODE -ne 0 -or $newKey.Length -ne 44) { throw 'No se pudo preparar la clave de cifrado local.' }
        Set-Content -LiteralPath $encryptionKeyFile -Value $newKey -NoNewline -Encoding ascii
    }
    $encryptionKey = (Get-Content -LiteralPath $encryptionKeyFile -Raw).Trim()

    if (-not (Test-Path -LiteralPath $Cloudflared)) {
        $toolsDir = Split-Path -Parent $Cloudflared
        New-Item -ItemType Directory -Path $toolsDir -Force | Out-Null
        $download = Join-Path $toolsDir 'cloudflared-download.tmp'
        $url = 'https://github.com/cloudflare/cloudflared/releases/download/2026.10.7/cloudflared-windows-amd64.exe'
        Write-Host 'Descargando cloudflared desde las publicaciones oficiales de Cloudflare…'
        Invoke-WebRequest -Uri $url -OutFile $download
        $actualHash = (Get-FileHash -LiteralPath $download -Algorithm SHA256).Hash.ToLowerInvariant()
        $expectedHash = '2493dbc168923bb3e59e5e7716f71deced92992eea9acd6e9d74f84ac7751343'
        if ($actualHash -ne $expectedHash) {
            Remove-Item -LiteralPath $download -Force -ErrorAction SilentlyContinue
            throw 'La comprobación de seguridad de cloudflared no coincide. No se ejecutó el archivo descargado.'
        }
        Move-Item -LiteralPath $download -Destination $Cloudflared -Force
    }

    $portProbe = [Net.Sockets.TcpClient]::new()
    try { $portProbe.Connect('127.0.0.1', 8765); $portBusy = $true }
    catch { $portBusy = $false }
    finally { $portProbe.Dispose() }
    if ($portBusy) { throw 'El puerto 8765 ya está ocupado. Cierra la app local antes de iniciar esta versión web.' }

    $env:SERRA_HOST = '127.0.0.1'
    $env:SERRA_PORT = '8765'
    $env:SERRA_APP_PASSWORD = $password
    $env:SERRA_SESSION_SECRET = Read-ProtectedValue 'session-secret'
    $env:SERRA_ENCRYPTION_KEY = $encryptionKey
    $env:SERRA_COOKIE_SECURE = '1'
    $env:SERRA_TUNNEL_MODE = '1'
    $env:PYTHONUNBUFFERED = '1'

    Remove-Item -LiteralPath $ServerOut, $ServerErr, $TunnelOut, $TunnelErr -Force -ErrorAction SilentlyContinue
    $ServerProcess = Start-Process -FilePath $Python -ArgumentList @('local_training_app.py') `
        -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $ServerOut -RedirectStandardError $ServerErr

    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        if ($ServerProcess.HasExited) { throw "El servidor local no pudo arrancar. Consulta $ServerErr" }
        try {
            $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8765/api/health' -TimeoutSec 2
            if ($response.StatusCode -eq 200) { $ready = $true; break }
        } catch { }
    }
    if (-not $ready) { throw 'El servidor no respondió en el puerto 8765. Revisa los registros locales de la app.' }

    $email = Read-Host 'Correo que recibirá el código de acceso de Cloudflare'
    if ($email -notmatch '^[^\s@]+@[^\s@]+\.[^\s@]+$') { throw 'Escribe una dirección de correo válida para proteger el túnel.' }

    Write-Host ''
    Write-Host 'Lolo Training App está iniciando. Deja esta ventana abierta.' -ForegroundColor Green
    Write-Host 'Cloudflare también pedirá un código enviado al correo indicado.'
    Write-Host 'Al terminar, pulsa Intro aquí para cerrar el acceso público.'
    Write-Host ''

    $configDir = Join-Path $LocalState 'cloudflared'
    New-Item -ItemType Directory -Path $configDir -Force | Out-Null
    $emptyConfig = Join-Path $configDir 'empty-config.yml'
    Set-Content -LiteralPath $emptyConfig -Value '{}' -Encoding ascii
    $tunnelArgs = @('--config', $emptyConfig, 'tunnel', '--url', 'http://127.0.0.1:8765', '--allowed-mail', $email)
    $TunnelProcess = Start-Process -FilePath $Cloudflared -ArgumentList $tunnelArgs `
        -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $TunnelOut -RedirectStandardError $TunnelErr

    $publicUrl = $null
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 1
        if ($TunnelProcess.HasExited) { throw "Cloudflare Tunnel se cerró. Revisa $TunnelOut y $TunnelErr" }
        if ((Test-Path -LiteralPath $TunnelOut) -or (Test-Path -LiteralPath $TunnelErr)) {
            $logText = (Get-Content -LiteralPath $TunnelOut -Raw -ErrorAction SilentlyContinue) + (Get-Content -LiteralPath $TunnelErr -Raw -ErrorAction SilentlyContinue)
            if ($logText -match 'https://[a-zA-Z0-9-]+\.trycloudflare\.com') { $publicUrl = $Matches[0]; break }
        }
    }
    if (-not $publicUrl) { throw "No apareció la dirección pública en un minuto. Revisa $TunnelOut y $TunnelErr" }

    Write-Host "Dirección pública: $publicUrl" -ForegroundColor Cyan
    Write-Host 'Guárdala en favoritos en el móvil. La dirección cambiará al reiniciar el túnel.'
    Write-Host 'Cuando Cloudflare solicite el código, introdúcelo; después inicia sesión en Lolo Training App.'
    Start-Process $publicUrl

    while (-not $TunnelProcess.HasExited) {
        if ([Console]::KeyAvailable) {
            $key = [Console]::ReadKey($true)
            if ($key.Key -eq [ConsoleKey]::Enter) { break }
        }
        Start-Sleep -Milliseconds 250
    }
}
catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    if ($TunnelProcess -and -not $TunnelProcess.HasExited) { Stop-Process -Id $TunnelProcess.Id -Force -ErrorAction SilentlyContinue }
    if ($ServerProcess -and -not $ServerProcess.HasExited) { Stop-Process -Id $ServerProcess.Id -Force -ErrorAction SilentlyContinue }
    foreach ($name in @('SERRA_APP_PASSWORD','SERRA_SESSION_SECRET','SERRA_ENCRYPTION_KEY','SERRA_TUNNEL_MODE')) {
        Remove-Item "Env:$name" -ErrorAction SilentlyContinue
    }
}
