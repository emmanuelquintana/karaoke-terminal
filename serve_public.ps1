# Lanza Terminal Karaoke (interfaz web) y lo expone en una URL pública
# mediante Cloudflare Tunnel (modo rápido, sin cuenta ni dominio).
#
# Uso:   ./serve_public.ps1            # puerto 8765 por defecto
#        ./serve_public.ps1 -Port 9000
#
# La app sigue corriendo SOLO en localhost; cloudflared (en esta misma
# máquina) es lo único que la expone, así el audio funciona porque sale
# por tu IP residencial. Detén todo con Ctrl+C.

param([int]$Port = 8765)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# Localiza cloudflared (PATH o ruta de instalación de winget)
$cf = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cf) {
    foreach ($p in @(
        "$env:ProgramFiles\cloudflared\cloudflared.exe",
        "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe"
    )) { if (Test-Path $p) { $cf = $p; break } }
}
if (-not $cf) {
    Write-Error "No encontré cloudflared. Instálalo con: winget install --id Cloudflare.cloudflared"
    exit 1
}

if (Test-Path "package.json") {
    $npm = (Get-Command npm -ErrorAction SilentlyContinue).Source
    if (-not $npm) {
        Write-Error "No encontré npm. Instala Node.js para compilar el frontend React antes de abrir el túnel."
        exit 1
    }

    if (-not (Test-Path "node_modules")) {
        Write-Host "Instalando dependencias del frontend..." -ForegroundColor Cyan
        & $npm install
    }

    Write-Host "Compilando frontend React..." -ForegroundColor Cyan
    & $npm run build
}

Write-Host "Iniciando el servidor en http://127.0.0.1:$Port ..." -ForegroundColor Cyan
$env:PYTHONIOENCODING = "utf-8"
$app = Start-Process -FilePath "python" `
    -ArgumentList "karaoke_web.py", "--no-open", "--host", "127.0.0.1", "--port", "$Port" `
    -PassThru -WindowStyle Minimized
Start-Sleep -Seconds 2

Write-Host "Abriendo tunel publico con Cloudflare (Ctrl+C para detener)..." -ForegroundColor Cyan
Write-Host "Busca la URL https://<algo>.trycloudflare.com en la salida de abajo." -ForegroundColor Yellow
try {
    & $cf tunnel --url "http://127.0.0.1:$Port" --no-autoupdate
}
finally {
    if ($app -and -not $app.HasExited) {
        Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue
        Write-Host "Servidor detenido." -ForegroundColor DarkGray
    }
}
