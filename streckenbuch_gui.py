"""Desktop GUI for the Streckenbuch PDF exporter.

The module can be imported without creating a Tk window.  This keeps the export
orchestration testable on headless systems; a window is only created by main().
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:  # Allow headless/import-only checks before the GUI extra is installed.
    DND_FILES = None
    TkinterDnD = None

from streckenbuch_export import (
    PROGRAM_NAME as APP_NAME,
    PROGRAM_VERSION as APP_VERSION,
    deduplicate_for_export,
    extract_pdf,
    output_paths,
    write_csv,
    write_ods,
    write_xlsx,
)

_FORMATS = {"xlsx", "ods", "csv", "all"}
StatusCallback = Callable[[str], None]


class ExportError(RuntimeError):
    """A user-facing export error."""


@dataclass(frozen=True)
class ExportResult:
    output_files: tuple[Path, ...]
    contact_count: int
    station_count: int
    duplicates_removed: int
    total_pages: int


def run_export(
    pdf_path: Path,
    output_directory: Path,
    output_format: str,
    status: StatusCallback | None = None,
) -> ExportResult:
    """Run the core exporter without touching Tk (safe for a worker thread)."""

    notify = status or (lambda _message: None)
    pdf_path = pdf_path.expanduser().resolve()
    output_directory = output_directory.expanduser().resolve()
    output_format = output_format.lower()

    if output_format not in _FORMATS:
        raise ExportError(f"Unbekanntes Ausgabeformat: {output_format}")
    if not pdf_path.is_file():
        raise ExportError(f"PDF-Datei nicht gefunden: {pdf_path}")
    if pdf_path.suffix.casefold() != ".pdf":
        raise ExportError("Bitte eine PDF-Datei auswählen.")
    if output_directory.exists() and not output_directory.is_dir():
        raise ExportError(f"Das Ausgabeziel ist kein Ordner: {output_directory}")

    try:
        output_directory.mkdir(parents=True, exist_ok=True)
        notify("PDF wird analysiert …")
        records, stations, total_pages = extract_pdf(pdf_path)

        notify("Fundstellen werden bereinigt …")
        records_before_deduplication = len(records)
        records = deduplicate_for_export(records)
        duplicates_removed = records_before_deduplication - len(records)

        output_base = output_directory / f"{pdf_path.stem}_rufnummern.xlsx"
        xlsx_path, ods_path, csv_path = output_paths(
            pdf_path, output_base, output_format
        )
        written: list[Path] = []

        if xlsx_path is not None:
            notify("XLSX-Datei wird geschrieben …")
            write_xlsx(
                records,
                stations,
                xlsx_path,
                source_pdf=pdf_path,
                total_pages=total_pages,
                duplicates_removed=duplicates_removed,
            )
            written.append(xlsx_path)

        if ods_path is not None:
            notify("ODS-Datei wird geschrieben …")
            write_ods(
                records,
                stations,
                ods_path,
                source_pdf=pdf_path,
                total_pages=total_pages,
                duplicates_removed=duplicates_removed,
            )
            written.append(ods_path)

        if csv_path is not None:
            notify("CSV-Datei wird geschrieben …")
            write_csv(records, csv_path)
            written.append(csv_path)
    except SystemExit as exc:
        # Core dependency errors use SystemExit for the CLI.  A GUI must keep
        # running and show the message instead of terminating the process.
        raise ExportError(str(exc) or "Der Export wurde unerwartet beendet.") from exc
    except PermissionError as exc:
        raise ExportError(f"Keine Berechtigung für Datei oder Ordner: {exc}") from exc
    except OSError as exc:
        raise ExportError(f"Dateifehler: {exc}") from exc

    return ExportResult(
        output_files=tuple(written),
        contact_count=len(records),
        station_count=len(stations),
        duplicates_removed=duplicates_removed,
        total_pages=total_pages,
    )


def dropped_path(raw_path: str) -> Path:
    """Convert a local drag-and-drop value, including file URLs, to a Path."""

    if raw_path.lower().startswith("file:"):
        parsed = urlparse(raw_path)
        path_text = url2pathname(unquote(parsed.path))
        if parsed.netloc and parsed.netloc.lower() != "localhost":
            path_text = f"//{parsed.netloc}{path_text}"
        return Path(path_text)
    return Path(raw_path)


class StreckenbuchGUI:
    """Tk desktop front end for the Streckenbuch exporter."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.pdf_var = tk.StringVar(master=root)
        self.output_dir_var = tk.StringVar(master=root)
        self.format_var = tk.StringVar(master=root, value="ods")
        self.status_var = tk.StringVar(master=root, value="Bereit")
        self._messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._controls: list[tk.Widget] = []

        self.root.title(APP_NAME)
        self.root.geometry("760x570")
        self.root.minsize(660, 520)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self.root.after(100, self._poll_messages)

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=(24, 20, 24, 12))
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)

        ttk.Label(main, text=APP_NAME, font=("TkDefaultFont", 18, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            main,
            text=(
                "Extrahiert Betriebsstellen und Rufnummern aus einem Streckenbuch-PDF "
                "und speichert sie als durchsuchbare Tabellendateien."
            ),
            wraplength=690,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(6, 18))

        pdf_frame = ttk.LabelFrame(main, text="1. Streckenbuch-PDF", padding=12)
        pdf_frame.grid(row=2, column=0, sticky="ew")
        pdf_frame.columnconfigure(0, weight=1)
        pdf_entry = ttk.Entry(pdf_frame, textvariable=self.pdf_var, state="readonly")
        pdf_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        browse_pdf = ttk.Button(pdf_frame, text="PDF auswählen …", command=self._pick_pdf)
        browse_pdf.grid(row=0, column=1)

        self.drop_area = tk.Label(
            pdf_frame,
            text="PDF hierher ziehen und ablegen",
            relief="groove",
            borderwidth=2,
            padx=12,
            pady=18,
            background="#f4f6f8",
            foreground="#334155",
        )
        self.drop_area.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        if DND_FILES is not None:
            self.drop_area.drop_target_register(DND_FILES)
            self.drop_area.dnd_bind("<<Drop>>", self._on_drop)
        else:
            self.drop_area.configure(
                text="Drag-and-drop benötigt tkinterdnd2 (PDF-Auswahl ist verfügbar)"
            )

        settings = ttk.Frame(main)
        settings.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        settings.columnconfigure(0, weight=1)
        settings.columnconfigure(1, weight=1)

        format_frame = ttk.LabelFrame(settings, text="2. Ausgabeformat", padding=12)
        format_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        for index, (value, label) in enumerate(
            (
                ("xlsx", "XLSX"),
                ("ods", "ODS"),
                ("csv", "CSV"),
                ("all", "Alle (XLSX, ODS, CSV)"),
            )
        ):
            button = ttk.Radiobutton(
                format_frame, text=label, value=value, variable=self.format_var
            )
            button.grid(row=index // 2, column=index % 2, sticky="w", padx=(0, 20), pady=3)
            self._controls.append(button)

        output_frame = ttk.LabelFrame(settings, text="3. Ausgabeordner", padding=12)
        output_frame.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        output_frame.columnconfigure(0, weight=1)
        output_entry = ttk.Entry(
            output_frame, textvariable=self.output_dir_var, state="readonly"
        )
        output_entry.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        browse_output = ttk.Button(
            output_frame, text="Ordner auswählen …", command=self._pick_output_directory
        )
        browse_output.grid(row=1, column=0, sticky="w")

        progress_frame = ttk.LabelFrame(main, text="Fortschritt", padding=12)
        progress_frame.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        progress_frame.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(progress_frame, mode="indeterminate")
        self.progress.grid(row=0, column=0, sticky="ew")
        ttk.Label(progress_frame, textvariable=self.status_var, wraplength=680).grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )

        self.export_button = ttk.Button(
            main, text="Export starten", command=self._start_export
        )
        self.export_button.grid(row=5, column=0, sticky="e", pady=(16, 0))
        self._controls.extend([browse_pdf, browse_output, self.export_button])

        footer = ttk.Frame(self.root, padding=(12, 7))
        footer.pack(side="bottom", fill="x")
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, text=APP_NAME).grid(row=0, column=0, sticky="w")
        ttk.Label(footer, text=f"Version {APP_VERSION}").grid(
            row=0, column=1, sticky="e"
        )

    def _pick_pdf(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.root,
            title="Streckenbuch-PDF auswählen",
            filetypes=(("PDF-Dateien", "*.pdf"), ("Alle Dateien", "*.*")),
        )
        if selected:
            self._set_pdf(Path(selected))

    def _set_pdf(self, path: Path) -> None:
        path = path.expanduser()
        if path.suffix.casefold() != ".pdf":
            messagebox.showerror(
                "Ungültige Datei", "Bitte eine PDF-Datei auswählen.", parent=self.root
            )
            return
        self.pdf_var.set(str(path))
        if not self.output_dir_var.get():
            self.output_dir_var.set(str(path.parent))
        self.status_var.set("Bereit")

    def _on_drop(self, event: object) -> str:
        data = getattr(event, "data", "")
        try:
            values = self.root.tk.splitlist(data)
        except tk.TclError:
            values = (data,)
        pdf_paths = [dropped_path(value) for value in values if value]
        selected = next(
            (path for path in pdf_paths if path.suffix.casefold() == ".pdf"), None
        )
        if selected is None:
            messagebox.showerror(
                "Ungültige Datei",
                "Die abgelegte Auswahl enthält keine PDF-Datei.",
                parent=self.root,
            )
        else:
            self._set_pdf(selected)
        return "break"

    def _pick_output_directory(self) -> None:
        initial = self.output_dir_var.get() or self.pdf_var.get()
        initial_directory = Path(initial)
        if initial_directory.is_file():
            initial_directory = initial_directory.parent
        selected = filedialog.askdirectory(
            parent=self.root,
            title="Ausgabeordner auswählen",
            initialdir=str(initial_directory) if initial else None,
            mustexist=True,
        )
        if selected:
            self.output_dir_var.set(selected)

    def _start_export(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        if not self.pdf_var.get():
            messagebox.showerror(
                "PDF fehlt", "Bitte zuerst eine PDF-Datei auswählen.", parent=self.root
            )
            return
        if not self.output_dir_var.get():
            messagebox.showerror(
                "Ausgabeordner fehlt",
                "Bitte einen Ausgabeordner auswählen.",
                parent=self.root,
            )
            return

        pdf_path = Path(self.pdf_var.get())
        output_directory = Path(self.output_dir_var.get())
        output_format = self.format_var.get()
        self._set_busy(True)
        self.status_var.set("Export wird vorbereitet …")
        self._worker = threading.Thread(
            target=self._export_worker,
            args=(pdf_path, output_directory, output_format),
            name="streckenbuch-export",
            daemon=True,
        )
        self._worker.start()

    def _export_worker(
        self, pdf_path: Path, output_directory: Path, output_format: str
    ) -> None:
        try:
            result = run_export(
                pdf_path,
                output_directory,
                output_format,
                status=lambda text: self._messages.put(("status", text)),
            )
        except Exception as exc:  # Report worker failures on Tk's main thread.
            message = str(exc).strip() or f"{type(exc).__name__}: unbekannter Fehler"
            self._messages.put(("error", message))
        else:
            self._messages.put(("success", result))

    def _poll_messages(self) -> None:
        try:
            while True:
                kind, payload = self._messages.get_nowait()
                if kind == "status":
                    self.status_var.set(str(payload))
                elif kind == "error":
                    self._set_busy(False)
                    self.status_var.set("Export fehlgeschlagen")
                    messagebox.showerror(
                        "Export fehlgeschlagen",
                        f"Der Export konnte nicht abgeschlossen werden.\n\n{payload}",
                        parent=self.root,
                    )
                elif kind == "success":
                    self._finish_export(payload)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_messages)

    def _finish_export(self, payload: object) -> None:
        if not isinstance(payload, ExportResult):
            self._set_busy(False)
            self.status_var.set("Export fehlgeschlagen")
            return
        self._set_busy(False)
        paths = "\n".join(str(path) for path in payload.output_files)
        summary = (
            f"Fertig: {payload.contact_count} eindeutige Fundstellen, "
            f"{payload.duplicates_removed} Dubletten entfernt, "
            f"{payload.station_count} Betriebsstellen."
        )
        self.status_var.set(summary)
        messagebox.showinfo(
            "Export abgeschlossen",
            f"{summary}\n\nErzeugte Dateien:\n{paths}",
            parent=self.root,
        )

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for control in self._controls:
            control.configure(state=state)
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()

    def _on_close(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            should_close = messagebox.askyesno(
                "Export läuft",
                "Der Export läuft noch. Beim Beenden können unvollständige Dateien "
                "zurückbleiben. Trotzdem beenden?",
                parent=self.root,
            )
            if not should_close:
                return
        self.root.destroy()


def main() -> int:
    if TkinterDnD is None:
        print(
            "tkinterdnd2 fehlt. Bitte die GUI-Abhängigkeiten installieren.",
            file=sys.stderr,
        )
        return 1
    try:
        root = TkinterDnD.Tk()
    except tk.TclError as exc:
        print(f"Tk-Fenster konnte nicht geöffnet werden: {exc}", file=sys.stderr)
        return 1
    StreckenbuchGUI(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
