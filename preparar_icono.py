"""Create Windows and Tk icon sizes from the user-provided logo, without redesigning it."""

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "assets" / "logo.png"


def main() -> None:
    with Image.open(SOURCE) as original:
        logo = original.convert("RGBA")
        if logo.width != logo.height:
            raise ValueError("El logo debe ser cuadrado para usarse como icono.")
        logo.save(ROOT / "assets" / "logo.ico", format="ICO",
                  sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                         (64, 64), (128, 128), (256, 256)])
        logo.resize((64, 64), Image.Resampling.LANCZOS).save(
            ROOT / "assets" / "logo-64.png")


if __name__ == "__main__":
    main()
