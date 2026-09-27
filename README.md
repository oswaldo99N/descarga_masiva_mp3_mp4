# Nexo Descargas

Aplicación de escritorio para Windows que descarga audio y video de YouTube, Facebook, Instagram, X y TikTok mediante `yt-dlp`. YouTube admite videos individuales y playlists. Los enlaces de las otras plataformas se tratan como publicaciones individuales.

## Instalación para usuarios

Descarga `Nexo-Descargas-Setup-X.Y.Z.exe` de una publicación oficial de Nexo Descargas y ejecútalo. El instalador crea un acceso en el menú Inicio, ofrece uno en el escritorio y añade el desinstalador a Windows. Incluye Python, yt-dlp, FFmpeg y Node.js: no tienes que instalarlos por separado. Las descargas y el historial permanecen en tu equipo.

Al abrir la aplicación se buscan nuevas versiones en [GitHub](https://github.com/oswaldo99N/descarga_masiva_mp3_mp4/releases). Si hay una, aparece un cuadro para actualizar o dejarlo para después; el botón **Actualizar** queda disponible. El instalador se descarga, se comprueba su SHA-256 y se abre tras tu confirmación. La publicación debe ser estable e incluir el instalador adjunto.

## Ejecutar desde el código fuente

Necesitas Python 3.10 o superior y conexión a Internet. En PowerShell, dentro de esta carpeta, ejecuta:

```powershell
powershell -ExecutionPolicy Bypass -File .\instalar.ps1
```

El script crea `.venv`, instala `yt-dlp` y prepara FFmpeg en `.tools` si hace falta. Para YouTube desde el código fuente también necesitas [Node.js 22+](https://nodejs.org/) o [Deno 2.3+](https://deno.com/).

Para crear un instalador en Windows, instala [Inno Setup 6](https://jrsoftware.org/isdl.php) y ejecuta:

```powershell
powershell -ExecutionPolicy Bypass -File .\crear_instalador.ps1
```

El script prepara una copia oficial de Node.js, verifica su SHA-256, empaqueta la app con PyInstaller y crea `dist/installer/Nexo-Descargas-Setup-X.Y.Z.exe`. Antes de publicar la próxima versión, cambia `APP_VERSION` en `release_config.py` y adjunta el instalador a una publicación estable del repositorio `oswaldo99N/descarga_masiva_mp3_mp4` con etiqueta `vX.Y.Z`. El repositorio de publicaciones debe ser público para que la app consulte su API sin credenciales. No subas `.venv`, `.tools`, `dist`, videos, historial ni cookies al repositorio.

Revisa `THIRD_PARTY_NOTICES.txt` y las obligaciones de distribución del código fuente de los componentes incluidos antes de publicar el instalador.

## Nueva descarga

1. Abre Nexo Descargas desde el menú Inicio, o `iniciar.bat` si usas el código fuente, y pega un enlace.
2. En YouTube, elige **Solo este video** o **Playlist completa** cuando corresponda.
3. Elige **Audio** o **Video**, la calidad, las opciones adicionales y la carpeta de destino.
4. Pulsa **Añadir e iniciar** para descargar o **Solo añadir** para dejar la tarea pendiente.

**Audio:** `Original` conserva el mejor flujo disponible y extrae el audio sin recodificar cuando la fuente lo permite. `MP3` lo convierte con FFmpeg; la conversión no mejora la calidad de la fuente.

**Video:** al leer un enlace individual, la aplicación muestra las alturas ofrecidas por la plataforma y permite elegir un límite. En playlists, las calidades pueden variar entre videos. `Automático` usa los mejores flujos disponibles. `MP4` exige flujos compatibles con MP4; si no existen, elige `MKV` o `Automático`. La aplicación no recodifica video para fabricar una resolución o un MP4 ausente.

**Sesión del navegador:** puedes elegir Chrome, Edge o Firefox para intentar acceder a contenido que requiere tu sesión iniciada. La aplicación lee las cookies del navegador seleccionado durante la vista previa y la descarga. En el historial solo guarda el nombre del navegador elegido; no guarda cookies ni contraseñas. El navegador puede pedir estar cerrado para permitir la lectura de cookies. Algunas restricciones de la plataforma pueden seguir impidiendo la descarga.

**Metadatos y portada:** `Añadir metadatos` incorpora los datos que entregue la plataforma; para audio se usa el artista si existe y, en su defecto, el nombre del canal o autor. `Guardar portada` conserva la imagen como archivo; con MP3 también intenta incrustarla en el audio. El resultado depende de los datos e imágenes disponibles en el enlace.

**Subtítulos:** para video, puedes guardar un `.srt` o incrustarlo y conservar el `.srt`. Elige español o inglés. Se usan subtítulos normales o automáticos si la plataforma los ofrece. Para incrustarlos, elige `MP4` o `MKV`.

## Cola e historial

La pestaña **Cola e historial** muestra cada tarea y su estado. **Iniciar / reanudar** procesa tareas pendientes y pausadas; **Pausar cola** detiene la tarea actual al siguiente punto de control. **Detener actual** deja esa tarea pausada y permite que la cola continúe. **Reintentar selección** vuelve a poner una tarea en marcha. **Quitar de la lista** elimina su registro, pero conserva los archivos descargados.

El historial se guarda en `%LOCALAPPDATA%\NexoDescargas\queue.json`. Cada tarea tiene un archivo de registro en `archives/` dentro de esa carpeta para omitir elementos ya completados al reintentar. Al ejecutar el código fuente actualizado por primera vez, se copia automáticamente el historial anterior de `.state/` si todavía no hay otro historial en la nueva ubicación. La copia original se conserva. Si cierras la aplicación durante una descarga, esa tarea aparecerá pausada cuando vuelvas a abrirla. La descarga no se inicia automáticamente al abrir el programa. Los archivos parciales pueden reanudarse y los archivos existentes no se sobrescriben.

Si un elemento de una playlist está eliminado, es privado o no está disponible, la aplicación intenta continuar con los demás y muestra el estado **Con errores** al terminar. Los Mix de YouTube son dinámicos; su número de elementos puede cambiar entre la vista previa y la descarga.

Descarga contenido para el que tengas permiso. Los contenidos privados, de pago, restringidos o protegidos pueden no estar disponibles incluso con una sesión iniciada.

## Estructura

- `providers.py`: reconoce enlaces y define el alcance de cada plataforma.
- `downloader.py`: selección de formatos, extracción y seguimiento de progreso.
- `queue_store.py`: cola persistente, historial y registro de elementos completados.
- `app_paths.py`: ubicación de datos del usuario y recursos empaquetados.
- `update_service.py`: consulta de versiones y descarga verificada del instalador.
- `app.py`: interfaz de Windows.

## Actualizar el motor

```powershell
.\.venv\Scripts\python.exe -m pip install -U "yt-dlp[default]"
```
