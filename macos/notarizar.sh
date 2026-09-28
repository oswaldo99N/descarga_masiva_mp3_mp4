#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${CODESIGN_IDENTITY:-}" || -z "${APPLE_ID:-}" || \
      -z "${APPLE_APP_SPECIFIC_PASSWORD:-}" || -z "${APPLE_TEAM_ID:-}" ]]; then
    echo "Sin credenciales de notarización: el DMG queda como artefacto de prueba."
    exit 0
fi

root="$(cd "$(dirname "$0")/.." && pwd)"
version="$("$root/.venv-macos/bin/python" -c 'from release_config import APP_VERSION; print(APP_VERSION)')"
case "$(uname -m)" in
    arm64) architecture=arm64 ;;
    x86_64) architecture=x64 ;;
    *) echo 'Arquitectura Mac no compatible.' >&2; exit 1 ;;
esac
dmg="$root/dist/macos/$architecture/Nexo-Descargas-$version-macos-$architecture.dmg"
codesign --verify --verbose=2 "$dmg"
xcrun notarytool submit "$dmg" --apple-id "$APPLE_ID" \
    --password "$APPLE_APP_SPECIFIC_PASSWORD" --team-id "$APPLE_TEAM_ID" --wait
xcrun stapler staple "$dmg"
xcrun stapler validate "$dmg"
echo "DMG firmado y notarizado: $dmg"
