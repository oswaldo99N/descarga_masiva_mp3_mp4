#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != Darwin ]]; then
    echo "Este script debe ejecutarse en macOS." >&2
    exit 1
fi

root="$(cd "$(dirname "$0")" && pwd)"
tools_dir="$root/.tools/macos"
mkdir -p "$tools_dir/node" "$tools_dir/static/lib" "$tools_dir/static/pkgconfig" "$tools_dir/source"

node_version=24.15.0
ffmpeg_version=9.0.2
node_arch="$(uname -m)"
case "$node_arch" in
    arm64) node_arch=arm64 ;;
    x86_64) node_arch=x64 ;;
    *) echo "Arquitectura de Mac no compatible: $node_arch" >&2; exit 1 ;;
esac

node_archive="node-v${node_version}-darwin-${node_arch}.tar.xz"
node_base="https://nodejs.org/download/release/v${node_version}"
curl --fail --location --retry 3 --silent --show-error "$node_base/SHASUMS256.txt" \
    --output "$tools_dir/source/node-shasums.txt"
expected_node_hash="$(awk -v file="$node_archive" '$2 == file {print $1}' "$tools_dir/source/node-shasums.txt")"
if [[ -z "$expected_node_hash" ]]; then
    echo "No se encontró el hash oficial de $node_archive." >&2
    exit 1
fi
curl --fail --location --retry 3 --silent --show-error "$node_base/$node_archive" \
    --output "$tools_dir/source/$node_archive"
echo "$expected_node_hash  $tools_dir/source/$node_archive" | shasum -a 256 -c -
tar -xJf "$tools_dir/source/$node_archive" -C "$tools_dir/source"
cp "$tools_dir/source/node-v${node_version}-darwin-${node_arch}/bin/node" "$tools_dir/node/node"
cp "$tools_dir/source/node-v${node_version}-darwin-${node_arch}/LICENSE" "$tools_dir/node/LICENSE"
"$tools_dir/node/node" --version

for dependency in brew pkg-config; do
    if ! command -v "$dependency" >/dev/null 2>&1; then
        echo "Falta $dependency. Instala Homebrew y ejecuta: brew install lame pkgconf nasm" >&2
        exit 1
    fi
done
lame_prefix="$(brew --prefix lame)"
lame_static="$lame_prefix/lib/libmp3lame.a"
if [[ ! -f "$lame_static" ]]; then
    echo "Falta libmp3lame.a. Ejecuta: brew install lame" >&2
    exit 1
fi
cp "$lame_static" "$tools_dir/static/lib/libmp3lame.a"
curl --fail --location --retry 3 --silent --show-error \
    'https://downloads.sourceforge.net/project/lame/lame/4.0/lame-4.0.tar.gz' \
    --output "$tools_dir/source/lame-4.0.tar.gz"
echo "3df5124d5ad3a98312ffd7ba6a9b36230e4f8a3e66d3ce0f425e336c32d216eb  $tools_dir/source/lame-4.0.tar.gz" | shasum -a 256 -c -
tar -xzf "$tools_dir/source/lame-4.0.tar.gz" -C "$tools_dir/source"
cp "$tools_dir/source/lame-4.0/COPYING" "$tools_dir/lame-COPYING.txt"
cat > "$tools_dir/static/pkgconfig/libmp3lame.pc" <<EOF
prefix=$tools_dir/static
libdir=\${prefix}/lib
includedir=$lame_prefix/include
Name: libmp3lame
Description: Static LAME MP3 encoder for Nexo Descargas
Version: 4.0
Libs: \${libdir}/libmp3lame.a
Cflags: -I\${includedir}
EOF

ffmpeg_archive="ffmpeg-${ffmpeg_version}.tar.gz"
curl --fail --location --retry 3 --silent --show-error \
    "https://ffmpeg.org/releases/$ffmpeg_archive" \
    --output "$tools_dir/source/$ffmpeg_archive"
echo "0aa2b1de2a5698b20a23e93d539a9a8e82ca0117496c5bdf05d198805f42bb3b  $tools_dir/source/$ffmpeg_archive" | shasum -a 256 -c -
tar -xzf "$tools_dir/source/$ffmpeg_archive" -C "$tools_dir/source"
(
    cd "$tools_dir/source/ffmpeg-$ffmpeg_version"
    PKG_CONFIG_LIBDIR="$tools_dir/static/pkgconfig" ./configure \
        --prefix="$tools_dir/ffmpeg" \
        --disable-shared --enable-static --disable-ffplay --disable-doc \
        --enable-gpl --enable-version3 --enable-libmp3lame
    make -j "$(sysctl -n hw.ncpu)"
    make install
)

for executable in ffmpeg ffprobe; do
    "$tools_dir/ffmpeg/bin/$executable" -version | head -n 1
    if otool -L "$tools_dir/ffmpeg/bin/$executable" | tail -n +2 | \
        grep -E '/opt/homebrew/|/usr/local/(Cellar|opt)/|@rpath' >/dev/null; then
        echo "$executable depende de bibliotecas de Homebrew no incluidas." >&2
        exit 1
    fi
done
"$tools_dir/ffmpeg/bin/ffmpeg" -hide_banner -encoders \
    > "$tools_dir/source/ffmpeg-encoders.txt"
grep -q libmp3lame "$tools_dir/source/ffmpeg-encoders.txt"
echo "Node.js, FFmpeg y FFprobe para macOS listos."
