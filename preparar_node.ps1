$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$version = "24.15.0"
$filename = "node-v$version-win-x64.zip"
$target = Join-Path $PSScriptRoot ".tools\node"
if ((Test-Path -LiteralPath (Join-Path $target "node.exe")) -and
    (Test-Path -LiteralPath (Join-Path $target "LICENSE")) -and
    ((& (Join-Path $target "node.exe") --version) -eq "v$version")) {
    Write-Host "Node.js ya está preparado para el instalador."
    exit 0
}

$base = "https://nodejs.org/download/release/v$version"
$archive = Join-Path $PSScriptRoot ".tools\$filename"
$sumfile = Join-Path $PSScriptRoot ".tools\node-shasums.txt"
New-Item -ItemType Directory -Force -Path $target | Out-Null
try {
    & curl.exe --fail --location --silent --show-error "$base/SHASUMS256.txt" --output $sumfile
    if ($LASTEXITCODE -ne 0) { throw "No se pudo descargar la lista de hashes de Node.js." }
    $sums = Get-Content -LiteralPath $sumfile
    $line = ($sums | Where-Object { $_.Trim() -match "^[a-fA-F0-9]{64}\s+$([regex]::Escape($filename))$" } | Select-Object -First 1)
    if (-not $line) { throw "No se encontró SHA-256 para $filename." }
    $expected = ($line -split '\s+')[0].ToLowerInvariant()
    & curl.exe --fail --location --silent --show-error "$base/$filename" --output $archive
    if ($LASTEXITCODE -ne 0) { throw "No se pudo descargar el paquete oficial de Node.js." }
    $actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $expected) { throw "La verificación SHA-256 de Node.js falló." }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($archive)
    try {
        foreach ($name in @("node.exe", "LICENSE")) {
            $entry = $zip.Entries | Where-Object { $_.FullName -like "*/$name" } | Select-Object -First 1
            if (-not $entry) { throw "No se encontró $name en el paquete oficial de Node.js." }
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, (Join-Path $target $name), $true)
        }
    } finally {
        $zip.Dispose()
    }
} finally {
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive }
    if (Test-Path -LiteralPath $sumfile) { Remove-Item -LiteralPath $sumfile }
}
Write-Host "Node.js $version preparado."
