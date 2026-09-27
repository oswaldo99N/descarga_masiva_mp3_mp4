"""Convert the existing logo into a native macOS app icon."""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent
ICONSET = ROOT / ".tools" / "macos" / "NexoDescargas.iconset"
OUTPUT = ROOT / ".tools" / "macos" / "NexoDescargas.icns"


def main() -> None:
    ICONSET.mkdir(parents=True, exist_ok=True)
    with Image.open(ROOT / "assets" / "logo.png") as original:
        logo = original.convert("RGBA")
        for points in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                name = f"icon_{points}x{points}{'@2x' if scale == 2 else ''}.png"
                logo.resize((points * scale, points * scale), Image.Resampling.LANCZOS).save(
                    ICONSET / name)
    subprocess.run(["iconutil", "-c", "icns", str(ICONSET), "-o", str(OUTPUT)],
                   check=True)


if __name__ == "__main__":
    main()
