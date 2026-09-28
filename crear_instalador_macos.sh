#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != Darwin ]]; then
    echo "El instalador para Mac se debe crear desde macOS." >&2
    exit 1
fi

root="$(cd "$(dirname "$0")" && pwd)"
cd "$root"
arch="$(uname -m)"
case "$arch" in
    arm64) release_arch=arm64 ;;
    x86_64) release_arch=x64 ;;
    *) echo "Arquitectura no compatible: $arch" >&2; exit 1 ;;
esac

if [[ "${NEXO_SKIP_PREPARE:-}" != 1 ]]; then
    "${PYTHON:-python3}" -m venv .venv-macos
    "$root/.venv-macos/bin/python" -m pip install --disable-pip-version-check \
        -r requirements.txt -r requirements-build.txt
    bash "$root/preparar_dependencias_macos.sh"
fi
python="$root/.venv-macos/bin/python"
"$python" "$root/preparar_icono_macos.py"

version="$("$python" -c 'from release_config import APP_VERSION; print(APP_VERSION)')"
ffmpeg="$root/.tools/macos/ffmpeg/bin/ffmpeg"
ffprobe="$root/.tools/macos/ffmpeg/bin/ffprobe"
node="$root/.tools/macos/node/node"
output="$root/dist/macos/$release_arch"

arguments=(
    --noconfirm --clean --onedir --windowed
    --name 'Nexo Descargas'
    --osx-bundle-identifier com.oswaldo99n.nexodescargas
    --icon "$root/.tools/macos/NexoDescargas.icns"
    --collect-all yt_dlp --collect-all yt_dlp_ejs
    --copy-metadata yt-dlp --copy-metadata yt-dlp-ejs
    --add-binary "$ffmpeg:bin/ffmpeg"
    --add-binary "$ffprobe:bin/ffmpeg"
    --add-binary "$node:bin/node"
    --add-data "$root/.tools/macos/node/LICENSE:bin/node"
    --add-data "$root/.tools/macos/lame-COPYING.txt:licenses"
    --add-data "$root/assets/logo-64.png:assets"
    --add-data "$root/THIRD_PARTY_NOTICES_MACOS.txt:."
    --add-data "$root/licenses/GPL-3.0.txt:licenses"
    --distpath "$output"
    --workpath "$root/build/macos/$release_arch"
    --specpath "$root/build/macos/$release_arch"
)
if [[ -n "${CODESIGN_IDENTITY:-}" ]]; then
    arguments+=(--codesign-identity "$CODESIGN_IDENTITY")
fi
"$python" -m PyInstaller "${arguments[@]}" "$root/app.py"

bundle="$output/Nexo Descargas.app"
"$bundle/Contents/MacOS/Nexo Descargas" --smoke-test
codesign --verify --deep --strict --verbose=2 "$bundle"

stage="$root/build/macos/$release_arch/dmg"
mkdir -p "$stage"
ditto "$bundle" "$stage/Nexo Descargas.app"
ln -s /Applications "$stage/Aplicaciones"
dmg="$output/Nexo-Descargas-$version-macos-$release_arch.dmg"
hdiutil create -volname 'Nexo Descargas' -srcfolder "$stage" -format UDZO \
    -ov "$dmg"

if [[ -n "${CODESIGN_IDENTITY:-}" ]]; then
    codesign --force --timestamp --sign "$CODESIGN_IDENTITY" "$dmg"
    codesign --verify --verbose=2 "$dmg"
fi
echo "Instalador Mac listo: $dmg"
