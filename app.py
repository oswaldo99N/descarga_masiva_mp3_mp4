"""Desktop interface for Nexo Descargas."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from app_paths import resource_path
from downloader import (
    DownloadCancelled,
    DownloadOptions,
    MediaPreview,
    Progress,
    clean_error,
    download,
    ffmpeg_directory,
    inspect_media,
    node_executable,
    require_dependencies,
)
from providers import UnsupportedLink, parse_media_link
from queue_store import QueueStore
from release_config import (APP_VERSION, DEVELOPER_NAME, DEVELOPER_URL,
                            REPOSITORY, SUPPORT_URL)
from update_service import Release, check_for_update, download_installer


BG = "#f3f6fb"
SURFACE = "#ffffff"
INK = "#182943"
MUTED = "#63738b"
LINE = "#dce5f1"
ACCENT = "#1559c9"
ACCENT_HOVER = "#0d47a6"
SOFT = "#e9f1ff"
ERROR = "#b4233d"
ERROR_HOVER = "#921a32"
CHECK_INTERVAL_MS = 30 * 60 * 1000
RETRY_INTERVAL_MS = 5 * 60 * 1000
FOCUS_CHECK_SECONDS = 10 * 60

BROWSERS = {"Sin sesión": "none", "Chrome": "chrome", "Edge": "edge", "Firefox": "firefox"}
CONTAINERS = {"Automático": "auto", "MP4": "mp4", "MKV": "mkv"}
SUBTITLES = {"Sin subtítulos": "none", "Guardar .srt": "sidecar", "Incrustar y guardar": "embed"}
LANGUAGES = {"Español": "es", "Inglés": "en"}
STATUS_NAMES = {
    "pending": "Pendiente", "running": "Descargando", "paused": "Pausado",
    "done": "Completado", "partial": "Con errores", "error": "Error",
}


class App(tk.Tk):
    def __init__(self) -> None:
        if os.name == "nt":
            # Windows uses this identity to match the window to its shortcuts.
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "Oswaldo.NexoDescargas")
        super().__init__()
        self.title(f"Nexo Descargas {APP_VERSION}")
        self.geometry("1040x740")
        self.minsize(900, 700)
        self.configure(bg=BG)
        self.logo_image = tk.PhotoImage(file=str(resource_path("assets", "logo-64.png")))
        self.iconphoto(True, self.logo_image)
        if os.name == "nt":
            self.iconbitmap(default=str(resource_path("assets", "logo.ico")))
        self.protocol("WM_DELETE_WINDOW", self._close)

        self.store = QueueStore()
        history = self.store.snapshot()
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.runner: threading.Thread | None = None
        self.queue_paused = True  # Reopening the app never starts downloads silently.
        self.current_id: str | None = None
        self.current_cancel: threading.Event | None = None
        self.cancel_reason: str | None = None
        self.progress_by_task: dict[str, Progress] = {}
        self.preview_info: MediaPreview | None = None
        self.preview_key: tuple[str, str, str] | None = None
        self.current_link = None
        self._closed = False
        self._preview_timer: str | None = None
        self._poll_timer: str | None = None
        self._update_timer: str | None = None
        self._checking_updates = False
        self._downloading_update = False
        self.available_release: Release | None = None
        self._prompted_release_version: str | None = None
        self._last_update_check = 0.0

        self.url = tk.StringVar()
        self.scope = tk.StringVar(value="single")
        self.kind = tk.StringVar(value="audio")
        self.folder = tk.StringVar(value=str(history[-1].options.folder) if history
                                   else str(Path.home() / "Downloads"))
        self.browser = tk.StringVar(value="Sin sesión")
        self.container = tk.StringVar(value="Automático")
        self.subtitle_mode = tk.StringVar(value="Sin subtítulos")
        self.subtitle_language = tk.StringVar(value="Español")
        self.embed_metadata = tk.BooleanVar(value=False)
        self.save_thumbnail = tk.BooleanVar(value=False)
        self.quality_values = ["best"]

        self._style()
        self._build()
        self.url.trace_add("write", self._schedule_preview)
        self.scope.trace_add("write", self._schedule_preview)
        self.browser.trace_add("write", self._schedule_preview)
        self.kind.trace_add("write", self._refresh_options)
        self.container.trace_add("write", self._refresh_options)
        self.subtitle_mode.trace_add("write", self._refresh_options)
        self._refresh_options()
        self._render_queue()
        self._poll_timer = self.after(100, self._poll_events)
        if REPOSITORY:
            self._update_timer = self.after(3000, self._check_updates)
            self.bind("<FocusIn>", self._on_window_focus, add="+")

    def _style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Surface.TFrame", background=SURFACE)
        style.configure("TLabel", background=BG, foreground=INK, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Surface.TLabel", background=SURFACE, foreground=INK)
        style.configure("SurfaceMuted.TLabel", background=SURFACE, foreground=MUTED)
        style.configure("TRadiobutton", background=SURFACE, foreground=INK, font=("Segoe UI", 10))
        style.configure("TCheckbutton", background=SURFACE, foreground=INK, font=("Segoe UI", 10))
        style.map("TRadiobutton", background=[("active", SURFACE)])
        style.map("TCheckbutton", background=[("active", SURFACE)])
        style.configure("TEntry", fieldbackground=SURFACE, foreground=INK, padding=7)
        style.configure("TCombobox", fieldbackground=SURFACE, foreground=INK, padding=5)
        style.map("TCombobox", fieldbackground=[("readonly", SURFACE)])
        style.configure("TProgressbar", troughcolor=LINE, background=ACCENT, borderwidth=0)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(19, 8), font=("Segoe UI Semibold", 10),
                        background=BG, foreground=MUTED)
        style.map("TNotebook.Tab", background=[("selected", SURFACE), ("active", SOFT)],
                  foreground=[("selected", ACCENT), ("active", INK)])
        style.configure("Treeview", rowheight=31, font=("Segoe UI", 9),
                        background=SURFACE, fieldbackground=SURFACE, foreground=INK)
        style.map("Treeview", background=[("selected", SOFT)],
                  foreground=[("selected", INK)])
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 9),
                        background="#edf2f9", foreground=INK)

    def _label(self, parent, text: str, *, surface=False, muted=False, **kw):
        if surface:
            style = "SurfaceMuted.TLabel" if muted else "Surface.TLabel"
        else:
            style = "Muted.TLabel" if muted else "TLabel"
        return ttk.Label(parent, text=text, style=style, **kw)

    def _button(self, parent, title: str, command, *, secondary=False) -> tk.Button:
        return tk.Button(
            parent, text=title, command=command, font=("Segoe UI Semibold", 10),
            fg=INK if secondary else "#ffffff", bg=SURFACE if secondary else ACCENT,
            activeforeground=INK if secondary else "#ffffff",
            activebackground=SOFT if secondary else ACCENT_HOVER,
            disabledforeground=MUTED, relief="flat", bd=0, cursor="hand2",
            padx=15, pady=6, highlightthickness=1 if secondary else 0,
            highlightbackground=LINE,
        )

    def _panel(self, parent, padding=(18, 15)) -> ttk.Frame:
        shell = tk.Frame(parent, bg=SURFACE, highlightbackground=LINE, highlightthickness=1)
        shell.columnconfigure(0, weight=1)
        inner = ttk.Frame(shell, style="Surface.TFrame", padding=padding)
        inner.grid(row=0, column=0, sticky="nsew")
        inner.columnconfigure(0, weight=1)
        return shell, inner

    def _build(self) -> None:
        body = ttk.Frame(self, padding=(20, 12, 20, 9))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)

        header = ttk.Frame(body)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.columnconfigure(1, weight=1)
        ttk.Label(header, image=self.logo_image, background=BG).grid(
            row=0, column=0, rowspan=2, sticky="w", padx=(0, 13))
        ttk.Label(header, text="Nexo Descargas", font=("Segoe UI Semibold", 23),
                  foreground=INK, background=BG).grid(row=0, column=1, sticky="sw")
        self._label(header, "Audio y video de YouTube, Facebook, Instagram, X y TikTok",
                    muted=True).grid(row=1, column=1, sticky="nw", pady=(1, 0))
        ttk.Label(header, text=f"Versión {APP_VERSION}", font=("Segoe UI", 9),
                  foreground=MUTED, background=BG).grid(row=0, column=2, sticky="ne", padx=(12, 0))

        self.tabs = ttk.Notebook(body)
        self.tabs.grid(row=2, column=0, sticky="nsew")
        self.new_tab = ttk.Frame(self.tabs, padding=(4, 7, 4, 0))
        self.queue_tab = ttk.Frame(self.tabs, padding=(4, 7, 4, 0))
        self.tabs.add(self.new_tab, text="Nueva descarga")
        self.tabs.add(self.queue_tab, text="Cola e historial")
        self._build_new_tab()
        self._build_queue_tab()

        footer = tk.Frame(body, bg=SURFACE, padx=14, pady=7,
                          highlightbackground=LINE, highlightthickness=1)
        footer.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        footer.columnconfigure(0, weight=1)
        self.status = ttk.Label(footer, text="Listo", background=SURFACE, foreground=INK,
                                font=("Segoe UI Semibold", 10), wraplength=480)
        self.status.grid(row=0, column=0, sticky="w")
        self.update_button = self._button(footer, "Buscar actualizaciones",
                                          lambda: self._check_updates(manual=True), secondary=True)
        self.update_button.grid(row=0, column=1, sticky="e")
        credit = tk.Button(
            footer, text=f"Desarrollado por {DEVELOPER_NAME}  ·  {DEVELOPER_URL.removeprefix('https://')}",
            command=lambda: self._open_website(DEVELOPER_URL),
            font=("Segoe UI", 9), fg=ACCENT, bg=SURFACE,
            activeforeground=ACCENT_HOVER, activebackground=SURFACE,
            relief="flat", bd=0, padx=0, pady=0, cursor="hand2",
            highlightthickness=0,
        )
        credit.grid(row=1, column=0, sticky="w", pady=(5, 0))
        if SUPPORT_URL.startswith("https://"):
            support = tk.Button(
                footer, text="Apoyar el desarrollo", command=lambda: self._open_website(SUPPORT_URL),
                font=("Segoe UI Semibold", 9), fg=ACCENT, bg=SURFACE,
                activeforeground=ACCENT_HOVER, activebackground=SURFACE,
                relief="flat", bd=0, padx=0, pady=0, cursor="hand2",
                highlightthickness=0,
            )
            support.grid(row=1, column=1, sticky="e", pady=(5, 0))

    def _build_new_tab(self) -> None:
        tab = self.new_tab
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)

        link_shell, link = self._panel(tab, (18, 7))
        link_shell.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._label(link, "Enlace de video o playlist", surface=True).grid(row=0, column=0, sticky="w")
        link_row = ttk.Frame(link, style="Surface.TFrame")
        link_row.grid(row=1, column=0, sticky="ew", pady=(4, 2))
        link_row.columnconfigure(0, weight=1)
        self.url_entry = ttk.Entry(link_row, textvariable=self.url, font=("Segoe UI", 11))
        self.url_entry.grid(row=0, column=0, sticky="ew", ipady=4)
        self._button(link_row, "Pegar", self._paste, secondary=True).grid(row=0, column=1,
                                                                     padx=(9, 0))
        self.preview = self._label(link, "Pega un enlace para ver sus detalles.", surface=True,
                                   muted=True, wraplength=830)
        self.preview.grid(row=2, column=0, sticky="w")

        left_shell, left = self._panel(tab, (18, 8))
        left_shell.grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=(7, 0))
        right_shell, right = self._panel(tab, (18, 8))
        right_shell.grid(row=1, column=1, sticky="nsew", padx=(8, 0), pady=(7, 0))

        self._label(left, "Descarga", surface=True,
                    font=("Segoe UI Semibold", 12)).grid(row=0, column=0, sticky="w")
        scopes = ttk.Frame(left, style="Surface.TFrame")
        scopes.grid(row=1, column=0, sticky="w", pady=(6, 6))
        self.single_radio = ttk.Radiobutton(scopes, text="Solo este video", variable=self.scope,
                                             value="single")
        self.single_radio.pack(side="left", padx=(0, 13))
        self.playlist_radio = ttk.Radiobutton(scopes, text="Playlist completa", variable=self.scope,
                                               value="playlist", state="disabled")
        self.playlist_radio.pack(side="left")
        kinds = ttk.Frame(left, style="Surface.TFrame")
        kinds.grid(row=2, column=0, sticky="w", pady=(0, 7))
        ttk.Radiobutton(kinds, text="Audio", variable=self.kind, value="audio").pack(
            side="left", padx=(0, 27))
        ttk.Radiobutton(kinds, text="Video", variable=self.kind, value="video").pack(side="left")

        choices = ttk.Frame(left, style="Surface.TFrame")
        choices.grid(row=3, column=0, sticky="ew")
        choices.columnconfigure(0, weight=1)
        choices.columnconfigure(1, weight=1)
        self._label(choices, "Audio", surface=True).grid(row=0, column=0, sticky="w")
        self._label(choices, "Calidad de video", surface=True).grid(row=0, column=1, sticky="w")
        self.audio_combo = ttk.Combobox(choices, state="readonly", width=19,
                                         values=("Original", "MP3"))
        self.audio_combo.current(0)
        self.audio_combo.grid(row=1, column=0, sticky="ew", padx=(0, 9), pady=(4, 6))
        self.quality_combo = ttk.Combobox(choices, state="disabled", width=19,
                                           values=("Mejor disponible",))
        self.quality_combo.current(0)
        self.quality_combo.grid(row=1, column=1, sticky="ew", pady=(4, 6))
        self._label(choices, "Contenedor de video", surface=True).grid(row=2, column=0,
                                                                    sticky="w")
        self.container_combo = ttk.Combobox(choices, state="readonly", width=19,
                                             textvariable=self.container,
                                             values=tuple(CONTAINERS))
        self.container_combo.grid(row=3, column=0, sticky="ew", padx=(0, 9), pady=(5, 0))
        self.available = self._label(choices, "", surface=True, muted=True,
                                     wraplength=200, justify="left")
        self.available.grid(row=2, column=1, rowspan=2, sticky="w", padx=(3, 0))

        self._label(right, "Opciones", surface=True,
                    font=("Segoe UI Semibold", 12)).grid(row=0, column=0, sticky="w")
        self._label(right, "Sesión del navegador", surface=True).grid(row=1, column=0,
                                                                    sticky="w", pady=(9, 0))
        self.browser_combo = ttk.Combobox(right, state="readonly", textvariable=self.browser,
                                           values=tuple(BROWSERS))
        self.browser_combo.grid(row=2, column=0, sticky="ew", pady=(4, 2))
        self._label(right, "Opcional para enlaces que piden iniciar sesión.", surface=True,
                    muted=True).grid(row=3, column=0, sticky="w")
        ttk.Checkbutton(right, text="Añadir metadatos", variable=self.embed_metadata).grid(
            row=4, column=0, sticky="w", pady=(6, 0))
        ttk.Checkbutton(right, text="Guardar portada", variable=self.save_thumbnail).grid(
            row=5, column=0, sticky="w", pady=(0, 5))
        subs = ttk.Frame(right, style="Surface.TFrame")
        subs.grid(row=6, column=0, sticky="ew")
        subs.columnconfigure(0, weight=1)
        subs.columnconfigure(1, weight=1)
        self._label(subs, "Subtítulos", surface=True).grid(row=0, column=0, sticky="w")
        self._label(subs, "Idioma", surface=True).grid(row=0, column=1, sticky="w")
        self.subtitle_combo = ttk.Combobox(subs, state="readonly", width=18,
                                            textvariable=self.subtitle_mode,
                                            values=tuple(SUBTITLES))
        self.subtitle_combo.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(5, 0))
        self.language_combo = ttk.Combobox(subs, state="readonly", width=12,
                                            textvariable=self.subtitle_language,
                                            values=tuple(LANGUAGES))
        self.language_combo.grid(row=1, column=1, sticky="ew", pady=(5, 0))

        bottom_shell, bottom = self._panel(tab, (18, 7))
        bottom_shell.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(7, 0))
        self._label(bottom, "Guardar en", surface=True).grid(row=0, column=0, sticky="w")
        folder_row = ttk.Frame(bottom, style="Surface.TFrame")
        folder_row.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        folder_row.columnconfigure(0, weight=1)
        ttk.Entry(folder_row, textvariable=self.folder).grid(row=0, column=0, sticky="ew", ipady=3)
        self._button(folder_row, "Elegir carpeta", self._choose_folder, secondary=True).grid(
            row=0, column=1, padx=(9, 0))

        actions = ttk.Frame(tab)
        actions.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        self._button(actions, "Añadir e iniciar", lambda: self._add(start=True)).pack(side="left")
        self._button(actions, "Solo añadir", lambda: self._add(start=False), secondary=True).pack(
            side="left", padx=(9, 0))
        self._button(actions, "Abrir carpeta", self._open_form_folder, secondary=True).pack(side="right")

    def _build_queue_tab(self) -> None:
        tab = self.queue_tab
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(tab)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self._button(toolbar, "Iniciar / reanudar", self._resume_queue).pack(side="left")
        self._button(toolbar, "Pausar cola", self._pause_queue, secondary=True).pack(
            side="left", padx=(8, 0))
        self._button(toolbar, "Detener actual", self._stop_current, secondary=True).pack(
            side="left", padx=(8, 0))

        table_frame = ttk.Frame(tab)
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(table_frame, columns=("platform", "type", "status", "progress",
                                                   "added"), show="tree headings", selectmode="browse",
                                 height=8)
        self.tree.heading("#0", text="Contenido")
        self.tree.column("#0", width=320, minwidth=190)
        for key, title, width in (("platform", "Plataforma", 100), ("type", "Tipo", 80),
                                  ("status", "Estado", 110), ("progress", "Progreso", 90),
                                  ("added", "Añadido", 115)):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, minwidth=70, stretch=key == "added")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self._show_selected)

        detail_shell, detail = self._panel(tab, (15, 8))
        detail_shell.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        self.task_detail = self._label(detail, "Selecciona una tarea para ver sus detalles.",
                                       surface=True, muted=True, wraplength=840)
        self.task_detail.grid(row=0, column=0, sticky="w")
        self.task_bar = ttk.Progressbar(detail, maximum=100)
        self.task_bar.grid(row=1, column=0, sticky="ew", pady=(9, 0))

        actions = ttk.Frame(tab)
        actions.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        self._button(actions, "Reintentar selección", self._retry_selected, secondary=True).pack(
            side="left")
        self._button(actions, "Quitar de la lista", self._remove_selected, secondary=True).pack(
            side="left", padx=(8, 0))
        self._button(actions, "Abrir carpeta", self._open_selected_folder, secondary=True).pack(
            side="right")

    def _set_message(self, text: str, *, error=False) -> None:
        self.status.configure(text=text, foreground=ERROR if error else INK)

    def _open_website(self, url: str) -> None:
        if not url.startswith("https://") or not webbrowser.open_new_tab(url):
            self._set_message("No se pudo abrir el enlace en el navegador.", error=True)

    def _paste(self) -> None:
        try:
            self.url.set(self.clipboard_get().strip())
        except tk.TclError:
            self._set_message("El portapapeles está vacío.", error=True)

    def _choose_folder(self) -> None:
        choice = filedialog.askdirectory(initialdir=self.folder.get() or str(Path.home()))
        if choice:
            self.folder.set(choice)

    def _open_folder(self, path: Path) -> None:
        if not path.is_dir():
            self._set_message("La carpeta aún no existe.", error=True)
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            os.startfile(path)

    def _open_form_folder(self) -> None:
        self._open_folder(Path(self.folder.get()).expanduser())

    def _open_selected_folder(self) -> None:
        item = self._selected_item()
        if item:
            self._open_folder(item.options.folder)

    def _preview_request(self) -> tuple[str, str, str]:
        return (self.url.get().strip(), self.scope.get(), BROWSERS[self.browser.get()])

    def _schedule_preview(self, *_args) -> None:
        if self._preview_timer is not None:
            self.after_cancel(self._preview_timer)
            self._preview_timer = None
        self.preview_info = None
        self.preview_key = None
        self._refresh_quality_choices()
        key = self._preview_request()
        self.preview.configure(text="Leyendo enlace…" if key[0] else "Pega un enlace para empezar.")
        self._preview_timer = self.after(550, self._inspect_if_current, key)

    def _inspect_if_current(self, key: tuple[str, str, str]) -> None:
        self._preview_timer = None
        if self._closed:
            return
        if key != self._preview_request():
            return
        try:
            link = parse_media_link(key[0])
        except UnsupportedLink as exc:
            self.preview.configure(text=str(exc))
            return
        self.current_link = link
        self.single_radio.configure(text="Solo este video" if link.provider == "YouTube"
                                    else "Solo este enlace",
                                    state="disabled" if link.playlist_only else "normal")
        self.playlist_radio.configure(state="normal" if link.has_playlist else "disabled")
        if link.playlist_only and self.scope.get() != "playlist":
            self.scope.set("playlist")
            return
        if not link.has_playlist and self.scope.get() != "single":
            self.scope.set("single")
            return

        def worker() -> None:
            try:
                preview = inspect_media(link, key[1], key[2])
                self.events.put(("preview", (key, preview, None)))
            except Exception as exc:
                self.events.put(("preview", (key, None, clean_error(str(exc)))))

        threading.Thread(target=worker, daemon=True).start()

    def _refresh_quality_choices(self) -> None:
        selected = self.quality_values[self.quality_combo.current()] if hasattr(
            self, "quality_combo") and self.quality_combo.current() >= 0 else "best"
        preview = self.preview_info
        if preview and self.scope.get() == "single" and preview.heights:
            heights = preview.mp4_heights if self.container.get() == "MP4" else preview.heights
            self.quality_values = ["best", *[str(height) for height in heights]]
            detail = ", ".join(f"{height}p" for height in heights[:5])
            self.available.configure(text=f"Disponibles: {detail}" if detail else "MP4 no disponible")
        elif self.scope.get() == "playlist":
            self.quality_values = ["best", "1080", "720", "480"]
            self.available.configure(text="La calidad varía en cada video")
        else:
            self.quality_values = ["best"]
            self.available.configure(text="Calidades al analizar el enlace")
        labels = ["Mejor disponible", *[f"Hasta {value}p" for value in self.quality_values[1:]]]
        self.quality_combo.configure(values=labels)
        self.quality_combo.current(self.quality_values.index(selected) if selected in self.quality_values else 0)

    def _refresh_options(self, *_args) -> None:
        is_audio = self.kind.get() == "audio"
        self.audio_combo.configure(state="readonly" if is_audio else "disabled")
        self.quality_combo.configure(state="disabled" if is_audio else "readonly")
        self.container_combo.configure(state="disabled" if is_audio else "readonly")
        self.subtitle_combo.configure(state="disabled" if is_audio else "readonly")
        self.language_combo.configure(state="disabled" if is_audio or
                                      self.subtitle_mode.get() == "Sin subtítulos" else "readonly")
        if not is_audio and self.subtitle_mode.get() == "Incrustar y guardar" and \
                self.container.get() == "Automático":
            self.container.set("MKV")
        self._refresh_quality_choices()

    def _collect_options(self) -> DownloadOptions:
        link = parse_media_link(self.url.get())
        scope = self.scope.get()
        if scope == "playlist" and not link.has_playlist:
            raise ValueError("El enlace no contiene una playlist.")
        if scope == "single" and link.playlist_only:
            raise ValueError("Selecciona Playlist completa para este enlace.")
        if not self.folder.get().strip():
            raise ValueError("Elige una carpeta de destino.")
        kind = self.kind.get()
        quality = self.quality_values[self.quality_combo.current()]
        container = CONTAINERS[self.container.get()]
        if (kind == "video" and container == "mp4" and self.preview_info and
                scope == "single" and self.preview_info.heights and
                not self.preview_info.mp4_heights):
            raise ValueError("Este enlace no ofrece video MP4. Elige MKV o Automático.")
        options = DownloadOptions(
            link=link,
            folder=Path(self.folder.get().strip()).expanduser(),
            scope=scope,
            kind=kind,
            quality=quality,
            audio_format="mp3" if self.audio_combo.current() == 1 else "original",
            browser=BROWSERS[self.browser.get()],
            embed_metadata=self.embed_metadata.get(),
            save_thumbnail=self.save_thumbnail.get(),
            subtitle_mode=SUBTITLES[self.subtitle_mode.get()] if kind == "video" else "none",
            subtitle_language=LANGUAGES[self.subtitle_language.get()],
            video_container=container if kind == "video" else "auto",
        )
        require_dependencies(options)
        return options

    def _add(self, *, start: bool) -> None:
        try:
            options = self._collect_options()
            title = (self.preview_info.title if self.preview_info and
                     self.preview_key == self._preview_request() else options.link.url)
            item, created = self.store.add_or_requeue(options, title)
        except (UnsupportedLink, ValueError, RuntimeError, OSError) as exc:
            self._set_message(clean_error(str(exc)), error=True)
            return
        self._render_queue(select=item.task_id)
        self.tabs.select(self.queue_tab)
        self._set_message("Añadido a la cola" if created else "Tarea existente actualizada")
        if start:
            self.queue_paused = False
            self._kick_queue()

    def _selected_item(self):
        selected = self.tree.selection()
        return self.store.get(selected[0]) if selected else None

    def _render_queue(self, *, select: str | None = None) -> None:
        selected = select or (self.tree.selection()[0] if self.tree.selection() else None)
        items = self.store.snapshot()
        for row in self.tree.get_children():
            self.tree.delete(row)
        for item in items:
            progress = self.progress_by_task.get(item.task_id)
            pct = f"{progress.percent:.0f}%" if progress and progress.percent is not None else ""
            if item.status == "done":
                pct = "100%"
            media_type = "Audio" if item.options.kind == "audio" else "Video"
            self.tree.insert("", "end", iid=item.task_id,
                             text=item.title[:95],
                             values=(item.options.link.provider, media_type,
                                     STATUS_NAMES.get(item.status, item.status), pct,
                                     item.created_at[0:16].replace("T", " ")))
        if selected and self.tree.exists(selected):
            self.tree.selection_set(selected)
            self.tree.see(selected)
        self._show_selected()

    def _show_selected(self, _event=None) -> None:
        item = self._selected_item()
        if not item:
            self.task_detail.configure(text="Selecciona una tarea para ver sus detalles.")
            self.task_bar.configure(value=0)
            return
        progress = self.progress_by_task.get(item.task_id)
        extra = f" · {item.transferred} transferidos"
        if item.errors:
            extra += f" · {item.errors} errores"
        if item.last_error:
            extra += f" · {item.last_error}"
        self.task_detail.configure(text=f"{item.options.link.url}\n{item.options.folder}{extra}")
        self.task_bar.configure(value=100 if item.status == "done" else
                                progress.percent if progress and progress.percent is not None else 0)

    def _kick_queue(self) -> None:
        if self.queue_paused or (self.runner and self.runner.is_alive()):
            return
        self.runner = threading.Thread(target=self._run_queue, daemon=True)
        self.runner.start()

    def _run_queue(self) -> None:
        while not self.queue_paused:
            item = self.store.next_pending()
            if not item:
                break
            self.current_id = item.task_id
            self.current_cancel = threading.Event()
            self.cancel_reason = None
            self.events.put(("refresh", item.task_id))
            options = replace(item.options, archive_path=self.store.archive_path(item.task_id))
            try:
                result = download(
                    options,
                    lambda progress: self.events.put(("progress", (item.task_id, progress))),
                    self.current_cancel,
                )
                self.store.update(item.task_id,
                                  status="partial" if result.errors else "done",
                                  transferred=item.transferred + result.transferred,
                                  errors=result.errors,
                                  last_error=result.last_error or "")
            except DownloadCancelled:
                should_resume = self.cancel_reason == "pause_queue" and not self.queue_paused
                self.store.update(item.task_id, status="pending" if should_resume else "paused")
            except Exception as exc:
                self.store.update(item.task_id, status="error", last_error=clean_error(str(exc)))
            self.events.put(("refresh", item.task_id))
            self.current_id = None
            self.current_cancel = None
            self.cancel_reason = None
        self.events.put(("idle", threading.current_thread()))

    def _resume_queue(self) -> None:
        self.store.resume_paused()
        self.queue_paused = False
        self._render_queue()
        self._set_message("Cola en marcha")
        self._kick_queue()

    def _pause_queue(self) -> None:
        self.queue_paused = True
        if self.current_cancel:
            self.cancel_reason = "pause_queue"
            self.current_cancel.set()
        self._set_message("Pausando cola…")

    def _stop_current(self) -> None:
        if self.current_cancel:
            self.cancel_reason = "stop_current"
            self.current_cancel.set()
            self._set_message("Deteniendo tarea actual…")

    def _retry_selected(self) -> None:
        item = self._selected_item()
        if not item or item.status == "running":
            return
        self.store.update(item.task_id, status="pending", errors=0, last_error="")
        self._render_queue(select=item.task_id)
        self.queue_paused = False
        self._kick_queue()

    def _remove_selected(self) -> None:
        item = self._selected_item()
        if item and self.store.remove(item.task_id):
            self.progress_by_task.pop(item.task_id, None)
            self._render_queue()
            self._set_message("Tarea quitada del historial; los archivos se conservan")

    def _schedule_update_check(self, delay_ms: int) -> None:
        if self._closed or not REPOSITORY:
            return
        if self._update_timer is not None:
            self.after_cancel(self._update_timer)
        self._update_timer = self.after(delay_ms, self._check_updates)

    def _on_window_focus(self, _event=None) -> None:
        if self._last_update_check and time.monotonic() - self._last_update_check >= FOCUS_CHECK_SECONDS:
            self._check_updates()

    def _show_update_button(self, release: Release | None, *, retry: bool = False) -> None:
        if release:
            self.update_button.configure(
                state="normal", command=self._install_update,
                text=f"Actualización {release.version} disponible",
                bg=ERROR, fg="#ffffff", activebackground=ERROR_HOVER,
                activeforeground="#ffffff", highlightbackground=ERROR,
            )
        else:
            self.update_button.configure(
                state="normal", command=lambda: self._check_updates(manual=True),
                text="Reintentar búsqueda" if retry else "Buscar actualizaciones",
                bg=SURFACE, fg=INK, activebackground=SOFT,
                activeforeground=INK, highlightbackground=LINE,
            )

    def _check_updates(self, *, manual: bool = False) -> None:
        if self._closed or self._checking_updates or self._downloading_update:
            return
        if self._update_timer is not None:
            self.after_cancel(self._update_timer)
            self._update_timer = None
        if not REPOSITORY:
            if manual:
                self._set_message("Las actualizaciones se activan al publicar el repositorio.")
            return
        self._checking_updates = True
        self._last_update_check = time.monotonic()
        if not self.available_release:
            self.update_button.configure(state="disabled", text="Buscando…")

        def worker() -> None:
            try:
                release = check_for_update()
                self.events.put(("update_check", (release, manual, None)))
            except Exception as exc:
                self.events.put(("update_check", (None, manual, str(exc))))

        threading.Thread(target=worker, daemon=True).start()

    def _install_update(self) -> None:
        release = self.available_release
        if not release or self._downloading_update:
            return
        if self.current_cancel or (self.runner and self.runner.is_alive()):
            messagebox.showinfo("Actualización", "Espera a que termine la tarea actual.", parent=self)
            return
        notes = release.notes.strip()[:900] or "Nueva versión disponible."
        if not messagebox.askyesno("Actualizar Nexo Descargas",
                                   f"Versión {release.version}\n\n{notes}\n\n"
                                   "Se descargará el instalador y se cerrará la aplicación. ¿Continuar?",
                                   parent=self):
            return
        self._downloading_update = True
        self.update_button.configure(state="disabled", text="Descargando…")
        self._set_message(f"Descargando actualización {release.version}…")

        def worker() -> None:
            try:
                installer = download_installer(release)
                self.events.put(("update_ready", installer))
            except Exception as exc:
                self.events.put(("update_download_error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_events(self) -> None:
        self._poll_timer = None
        if self._closed:
            return
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "preview":
                    key, preview, error = payload
                    if key != self._preview_request():
                        continue
                    self.preview_key = key
                    self.preview_info = preview
                    if error:
                        self.preview.configure(text=f"No se pudo leer: {error}")
                    else:
                        link = parse_media_link(key[0])
                        if link.dynamic_playlist and key[1] == "playlist":
                            count_text = "Mix dinámico"
                        else:
                            count_text = f"{preview.count} elementos" if preview.count != 1 else "1 elemento"
                        self.preview.configure(text=f"{link.provider} · {preview.title} · {count_text}")
                    self._refresh_quality_choices()
                elif event == "progress":
                    task_id, progress = payload
                    self.progress_by_task[task_id] = progress
                    if self.tree.exists(task_id):
                        pct = f"{progress.percent:.0f}%" if progress.percent is not None else ""
                        self.tree.set(task_id, "progress", pct)
                    if task_id == self.current_id:
                        self._set_message(f"{progress.status}: {progress.title[:80]}")
                    self._show_selected()
                elif event == "refresh":
                    self._render_queue(select=payload)
                    item = self.store.get(payload)
                    if item and item.status in {"done", "partial", "error", "paused"}:
                        self._set_message(f"{STATUS_NAMES[item.status]}: {item.title[:70]}",
                                          error=item.status == "error")
                elif event == "idle":
                    if payload is not self.runner:
                        continue
                    self.runner = None
                    if not self.queue_paused and any(
                        item.status == "pending" for item in self.store.snapshot()
                    ):
                        self._kick_queue()
                    elif not self.queue_paused:
                        self._set_message("Cola finalizada")
                elif event == "update_check":
                    release, manual, error = payload
                    self._checking_updates = False
                    self._schedule_update_check(RETRY_INTERVAL_MS if error else CHECK_INTERVAL_MS)
                    if error:
                        if manual:
                            self._set_message(f"No se pudo buscar actualizaciones: {error}", error=True)
                        if not self.available_release:
                            self._show_update_button(None, retry=True)
                    elif release:
                        self.available_release = release
                        self._show_update_button(release)
                        self._set_message(f"Nueva versión {release.version} disponible")
                        if not manual and release.version != self._prompted_release_version:
                            self._prompted_release_version = release.version
                            self.after_idle(self._install_update)
                    else:
                        self.available_release = None
                        self._show_update_button(None)
                        if manual:
                            self._set_message(f"Nexo Descargas {APP_VERSION} está actualizado")
                elif event == "update_download_error":
                    self._downloading_update = False
                    self._show_update_button(self.available_release)
                    self._set_message(f"No se pudo actualizar: {payload}", error=True)
                elif event == "update_ready":
                    self._downloading_update = False
                    try:
                        if sys.platform == "darwin":
                            subprocess.Popen(["open", str(payload)], cwd=str(payload.parent))
                        else:
                            subprocess.Popen([str(payload), "/CLOSEAPPLICATIONS"],
                                             cwd=str(payload.parent))
                    except OSError as exc:
                        self._show_update_button(self.available_release)
                        self._set_message(f"No se pudo abrir el instalador: {exc}", error=True)
                    else:
                        if sys.platform == "darwin":
                            messagebox.showinfo(
                                "Actualizar Nexo Descargas",
                                "Se abrió el instalador. Arrastra Nexo Descargas a Aplicaciones "
                                "para sustituir la versión anterior.", parent=self)
                        self._close()
                        return
        except queue.Empty:
            pass
        self._poll_timer = self.after(100, self._poll_events)

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.queue_paused = True
        if self.current_cancel:
            self.current_cancel.set()
        for timer in (self._preview_timer, self._poll_timer, self._update_timer):
            if timer is not None:
                self.after_cancel(timer)
        self.destroy()


if __name__ == "__main__":
    if sys.argv[1:] == ["--smoke-test"]:
        ffmpeg_bin = ffmpeg_directory()
        node_bin = node_executable()
        if ffmpeg_bin is None or node_bin is None:
            raise RuntimeError("El paquete no incluye FFmpeg, FFprobe y Node.js.")
        for command, option in (
            (ffmpeg_bin / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg"), "-version"),
            (ffmpeg_bin / ("ffprobe.exe" if os.name == "nt" else "ffprobe"), "-version"),
            (node_bin, "--version"),
        ):
            subprocess.run([str(command), option], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        app = App()
        app.update_idletasks()
        app._close()
    else:
        App().mainloop()
