#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${MACOS_CERTIFICATE_P12:-}" ]]; then
    if [[ -n "${CODESIGN_IDENTITY:-}" ]]; then
        echo "Falta MACOS_CERTIFICATE_P12 para firmar con Developer ID." >&2
        exit 1
    fi
    echo "Sin certificado: se generará un DMG de prueba con firma ad hoc."
    exit 0
fi
if [[ -z "${MACOS_CERTIFICATE_PASSWORD:-}" || -z "${CODESIGN_IDENTITY:-}" ]]; then
    echo "Faltan MACOS_CERTIFICATE_PASSWORD o MACOS_SIGN_IDENTITY." >&2
    exit 1
fi

keychain_dir="$(mktemp -d)"
keychain="$keychain_dir/nexo-build.keychain-db"
keychain_password="$(openssl rand -hex 24)"
certificate="$keychain_dir/certificate.p12"
CERTIFICATE_PATH="$certificate" python3 -c 'import base64, os, pathlib; pathlib.Path(os.environ["CERTIFICATE_PATH"]).write_bytes(base64.b64decode(os.environ["MACOS_CERTIFICATE_P12"]))'
security create-keychain -p "$keychain_password" "$keychain"
security set-keychain-settings -lut 21600 "$keychain"
security unlock-keychain -p "$keychain_password" "$keychain"
security import "$certificate" -k "$keychain" -P "$MACOS_CERTIFICATE_PASSWORD" \
    -T /usr/bin/codesign
security list-keychains -d user -s "$keychain"
security set-key-partition-list -S apple-tool:,apple: -s -k "$keychain_password" "$keychain"
rm -f "$certificate"
security find-identity -v -p codesigning "$keychain"
echo "Certificado Developer ID importado en un llavero temporal."
