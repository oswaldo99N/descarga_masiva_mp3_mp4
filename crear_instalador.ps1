param([string]$InnoCompiler = "")

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Ejecuta instalar.ps1 primero."
}
if (-not (Test-Path -LiteralPath ".tools\ffmpeg\ffmpeg.exe") -or
    -not (Test-Path -LiteralPath ".tools\ffmpeg\ffprobe.exe")) {
    throw "Faltan FFmpeg y FFprobe dentro de .tools\ffmpeg. Ejecuta instalar.ps1."
}
& (Join-Path $PSScriptRoot "preparar_node.ps1")

& $python -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw "No se pudo instalar PyInstaller." }
& $python preparar_icono.py
if ($LASTEXITCODE -ne 0) { throw "No se pudo preparar el icono." }
$version = (& $python -c "from release_config import APP_VERSION; print(APP_VERSION)").Trim()
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+\.\d+$') {
    throw "La versión de release_config.py debe tener formato X.Y.Z."
}

$arguments = @(
    "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
    "--name", "NexoDescargas",
    "--icon", "assets\logo.ico",
    "--collect-all", "yt_dlp", "--collect-all", "yt_dlp_ejs",
    "--copy-metadata", "yt-dlp", "--copy-metadata", "yt-dlp-ejs",
    "--add-binary", ".tools\ffmpeg\ffmpeg.exe;bin\ffmpeg",
    "--add-binary", ".tools\ffmpeg\ffprobe.exe;bin\ffmpeg",
    "--add-binary", ".tools\node\node.exe;bin\node",
    "--add-data", ".tools\node\LICENSE;bin\node",
    "--add-data", "assets\logo-64.png;assets",
    "--add-data", "assets\logo.ico;assets",
    "app.py"
)
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw "PyInstaller no pudo crear NexoDescargas.exe." }

if (-not $InnoCompiler) {
    $InnoCompiler = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $InnoCompiler -or -not (Test-Path -LiteralPath $InnoCompiler)) {
    throw "Instala Inno Setup 6 desde https://jrsoftware.org/isdl.php y vuelve a ejecutar este script."
}
& $InnoCompiler "/DAppVersion=$version" "installer.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup no pudo crear el instalador." }
Write-Host "Instalador listo: dist\installer\Nexo-Descargas-Setup-$version.exe"
