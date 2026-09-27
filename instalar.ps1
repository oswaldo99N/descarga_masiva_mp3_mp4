$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Instala Python 3.10 o superior antes de continuar."
}

if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "No se pudo crear el entorno de Python." }
}

& ".venv\Scripts\python.exe" -m pip --version *> $null
if ($LASTEXITCODE -ne 0) {
    & ".venv\Scripts\python.exe" -m ensurepip --upgrade --default-pip
    if ($LASTEXITCODE -ne 0) { throw "No se pudo preparar pip en el entorno virtual." }
}

& ".venv\Scripts\python.exe" -m pip install --upgrade -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "No se pudo instalar yt-dlp. Revisa tu conexión a Internet." }

if (-not (Test-Path -LiteralPath ".tools\ffmpeg\ffmpeg.exe") -and
    (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or
     -not (Get-Command ffprobe -ErrorAction SilentlyContinue))) {
    Write-Host "Descargando FFmpeg para esta aplicación..."
    $archive = Join-Path $PSScriptRoot ".tools\ffmpeg-download.zip"
    $extract = Join-Path $PSScriptRoot ".tools\ffmpeg-extracted"
    $target = Join-Path $PSScriptRoot ".tools\ffmpeg"
    New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot ".tools") | Out-Null
    try {
        Invoke-WebRequest -Uri "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" `
            -OutFile $archive
        Expand-Archive -LiteralPath $archive -DestinationPath $extract -Force
        $binary = Get-ChildItem -LiteralPath $extract -Recurse -Filter ffmpeg.exe | Select-Object -First 1
        if (-not $binary) { throw "El paquete no contiene ffmpeg.exe." }
        $binFolder = $binary.Directory.FullName
        if (-not (Test-Path -LiteralPath (Join-Path $binFolder "ffprobe.exe"))) {
            throw "El paquete no contiene ffprobe.exe."
        }
        New-Item -ItemType Directory -Force -Path $target | Out-Null
        Copy-Item -LiteralPath (Join-Path $binFolder "ffmpeg.exe") -Destination $target
        Copy-Item -LiteralPath (Join-Path $binFolder "ffprobe.exe") -Destination $target
    } finally {
        if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive }
        $workspacePrefix = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\') + '\'
        $resolvedExtract = [IO.Path]::GetFullPath($extract)
        if (-not $resolvedExtract.StartsWith($workspacePrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Ruta de limpieza fuera del proyecto."
        }
        if (Test-Path -LiteralPath $extract) { Remove-Item -LiteralPath $extract -Recurse -Force }
    }
}

if (-not (Get-Command deno -ErrorAction SilentlyContinue) -and
    -not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Warning "Instala Node.js 22+ o Deno 2.3+ para el soporte completo de YouTube."
}

Write-Host "Instalación terminada. Abre iniciar.bat."
