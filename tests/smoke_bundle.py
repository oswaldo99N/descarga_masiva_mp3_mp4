"""Launch the bundled app with a restricted PATH to catch missing bundled tools."""

import os
import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    if sys.platform != "win32":
        return 0
    root = Path(__file__).resolve().parent.parent
    executable = (Path(sys.argv[1]) if len(sys.argv) > 1 else
                  root / "dist" / "NexoDescargas" / "NexoDescargas.exe")
    if not executable.is_file():
        raise SystemExit("Primero ejecuta crear_instalador.ps1")
    data = root / ".tmp" / "smoke_bundle_data"
    data.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["LOCALAPPDATA"] = str(data)
    environment["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    process = subprocess.Popen([str(executable)], cwd=root, env=environment,
                               startupinfo=startup)
    try:
        time.sleep(4)
        if process.poll() is not None:
            raise RuntimeError(f"El programa empaquetado salió con código {process.returncode}")
        print("NexoDescargas.exe inició y permaneció abierto con PATH restringido.")
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=10)
        if data.is_dir() and not any(data.iterdir()):
            data.rmdir()


if __name__ == "__main__":
    raise SystemExit(main())
