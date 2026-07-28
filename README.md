# Streckenbuch Export

Das Programm liest den Text eines Streckenbuch-PDFs, erkennt Strecken, Betriebsstellen und Rufnummern und schreibt schnell filterbare Dateien für Excel (`.xlsx`), LibreOffice Calc (`.ods`) und CSV.

## Exportierte Spalten

- Strecke und Streckenbezeichnung
- Betriebsstellenart und Betriebsstelle
- Stelle/Funktion (z. B. Fdl oder Ww)
- Kurzwahl, Langwahl, GSM-R-, T-Com- und funktionale Rufnummer
- Regelwerksbezug (Ril), PDF-Seite und gedruckte Seite
- Fundstellenart, Konfidenz und Originaltext zur Kontrolle

Die XLSX- und ODS-Dateien enthalten die Tabellen **Kontakte**, **Betriebsstellen** und **Info**. Rufnummern werden ausdrücklich als Text gespeichert, damit Tabellenprogramme sie nicht verändern. Alle erkannten Dubletten werden vor dem Export entfernt. Die Info-Tabelle nennt ihre Anzahl.

Die native ODS-Datei enthält Calc-Datenbankbereiche mit aktivierten Filterfeldern für jede Spalte der Tabellen **Kontakte** und **Betriebsstellen**. In LibreOffice stehen die Filter deshalb direkt in den Kopfzeilen zur Verfügung.

Als Dublette gilt derselbe Kontakt auf derselben Strecke und Betriebsstelle mit identischer Funktion und identischen Kurz-, Lang-, GSM-R-, T-Com- und funktionalen Rufnummern. Fundseite, Ril, Konfidenz und Originaltext ändern diese fachliche Identität nicht; beim Zusammenführen bleibt die erste Fundstelle erhalten.

## Browser-Version und GitHub Pages

Die statische Web-Oberfläche unter `web/` führt denselben Python-Parser über Pyodide/WebAssembly in einem Web Worker aus. Die gewählte PDF bleibt im Browser und wird nicht an einen Server übertragen. Beim ersten Export werden Pyodide sowie `pypdf`, `openpyxl` und `odfpy` aus dem Internet geladen. Anschließend stehen XLSX, ODS und CSV als lokale Downloads bereit.

Lokal bauen und testen:

```bash
make web-build
make web-serve
# http://localhost:8000 öffnen
```

`make web-build` erzeugt das nicht versionierte Artefakt unter `dist/pages/` und kopiert den aktuellen Produktionsparser hinein. Die Tests prüfen, dass alle lokalen Assets und exakt dieser Parser enthalten sind.

Der Workflow `.github/workflows/deploy-pages.yml` veröffentlicht bei jedem Push auf `main`. Im GitHub-Repository muss einmalig unter **Settings → Pages → Build and deployment → Source** die Quelle **GitHub Actions** gewählt werden. Danach ist die Anwendung unter `https://mi-skam.github.io/streckenbuch-export/` erreichbar.

Browser-Grenzen: Die Verarbeitung ist seriell und benötigt für große PDFs deutlich mehr Arbeitsspeicher als die Desktop-Version. Passwortgeschützte PDFs werden nicht unterstützt. Für sehr große Dokumente oder Offline-Betrieb bleibt die Desktop-Version die zuverlässigere Variante.

## Desktop-Oberfläche

```bash
make setup
make gui
```

Das Fenster bietet:

- PDF-Auswahl über den nativen Dateidialog
- ein Drag-and-drop-Feld für PDF-Dateien
- Auswahl zwischen ODS, XLSX, CSV und allen Formaten
- Auswahl des Ausgabeordners
- Export im Hintergrund mit Statusanzeige
- Programmname links und Versionsnummer rechts in der Fußzeile

Ein fertig gebautes Desktop-Programm startet direkt diese Oberfläche; eine separate Python-Installation ist dafür nicht erforderlich.

## Entwicklungsumgebung mit Nix

Die Flake stellt Python sowie alle Laufzeit- und Entwicklungsabhängigkeiten bereit, einschließlich Tk, tkinterdnd2, PyInstaller, pytest und uv:

```bash
nix develop
pytest
```

Unterstützt werden Linux und macOS auf `x86_64` und `aarch64`. `flake.lock` hält die verwendete nixpkgs-Version reproduzierbar fest.

## Entwicklungs-Lifecycle mit Make

```bash
make help
make setup
make check
```

Direkte Exporte:

```bash
make export-ods  PDF="/Pfad/Streckenbuch.pdf" OUTPUT="/Pfad/streckenbuch.ods"
make export-xlsx PDF="/Pfad/Streckenbuch.pdf"
make export-csv  PDF="/Pfad/Streckenbuch.pdf"
make export-all  PDF="/Pfad/Streckenbuch.pdf" OUTPUT="/Pfad/streckenbuch"
```

Optional können `PAGES="15-30,42"` und `MIN_CONFIDENCE=0.8` gesetzt werden. `make clean` entfernt Build-Artefakte und Caches; `make distclean` zusätzlich die virtuelle Umgebung.

## Desktop-Executables

Ein lokaler PyInstaller-Build erzeugt immer ein Programm für das Betriebssystem, auf dem der Build läuft:

```bash
make build
# oder explizit: make build-macos / make build-linux / make build-windows
```

PyInstaller unterstützt keine verlässliche Cross-Kompilierung. Die Datei `.github/workflows/build-binaries.yml` baut deshalb nativ auf Windows, macOS und Linux. Eine unversionierte Build-Matrix kann so gestartet werden:

```bash
make build-all
```

Ein Tag erzeugt zusätzlich eine öffentliche GitHub-Release mit allen Downloads:

```bash
make release TAG=v0.4.2
```

Die Release enthält Windows x86_64, Linux x86_64 sowie getrennte macOS-Builds für Apple Silicon und Intel: `StreckenbuchExport-windows-x86_64-<Tag>.zip`, `StreckenbuchExport-macos-arm64-<Tag>.zip`, `StreckenbuchExport-macos-x86_64-<Tag>.zip` und `StreckenbuchExport-linux-x86_64-<Tag>.tar.gz`. Die Builds sind derzeit nicht codesigniert; macOS Gatekeeper oder Windows SmartScreen können daher beim ersten Start eine Warnung anzeigen.

## Installation und Kommandozeile

Mit `uv`:

```bash
cd ~/Desktop/streckenbuch-export
uv sync
uv run python streckenbuch_export.py \
  ~/Desktop/AngStrebu_Süd_20251214_interaktiv\(1\).pdf \
  --format all
```

Native LibreOffice-Datei erzeugen:

```bash
uv run python streckenbuch_export.py DATEI.pdf --format ods
```

Alle drei Formate erzeugen:

```bash
uv run python streckenbuch_export.py DATEI.pdf --format all
```

`--format both` bleibt aus Kompatibilitätsgründen die Kombination XLSX und CSV. Nur einige PDF-Seiten zum schnellen Testen:

```bash
uv run python streckenbuch_export.py DATEI.pdf --pages 15-30,42 --format ods
```

## Parallele PDF-Verarbeitung und Benchmark

Die PDF-Textextraktion verwendet bei größeren Dokumenten mehrere Prozesse. Das anschließende Parsen bleibt bewusst nach PDF-Seite geordnet, weil Folgeseiten Strecke, Betriebsstelle und Regelkontext von der vorherigen Seite erben. Die Automatik berücksichtigt die für den Prozess verfügbaren CPUs, die Seitenzahl und einen Speicher-schonenden Höchstwert von acht Prozessen. Kleine Dokumente mit weniger als 20 Seiten bleiben seriell.

Die Auswahl kann überschrieben werden: `--workers 1` arbeitet vollständig seriell, `--workers 4` fordert bis zu vier Prozesse an und `--workers 0` aktiviert die Automatik (Standard). Die tatsächliche Anzahl wird immer durch verfügbare CPUs und Seiten begrenzt.

Ein reproduzierbarer Skalierungstest probiert schrittweise jede Workerzahl von 1 bis zur effektiven CPU-Anzahl aus und prüft dabei, dass das Parsergebnis identisch bleibt:

```bash
nix develop --command python benchmark_parallel.py DATEI.pdf --repeats 3
# optional begrenzen:
nix develop --command python benchmark_parallel.py DATEI.pdf --pages 100 --max-workers 8
```

`os.process_cpu_count()` wird verwendet, wenn es verfügbar ist. Auf älteren Python-Versionen folgen Affinitätsmaske und `os.cpu_count()` als portable Rückfälle, damit Container, Linux, macOS und Windows mit unterschiedlichen Kernzahlen sinnvoll behandelt werden.

Ausgabeziel selbst festlegen:

```bash
uv run python streckenbuch_export.py DATEI.pdf --format ods -o ~/Desktop/streckenbuch_suche.ods
```

Bei `--format all` wird die angegebene Dateiendung als Ausgabestamm verwendet und es entstehen `.xlsx`, `.ods` und `.csv`.

Tests:

```bash
uv run pytest
```

## Grenzen des Prototyps

PDF-Dateien speichern Tabellen häufig nicht in ihrer sichtbaren Zeilen-/Spaltenreihenfolge. Der Parser nutzt deshalb Heuristiken. Die Spalte **Originaltext** und eine Konfidenzbewertung machen unsichere Zuordnungen kontrollierbar. Besonders mehrspaltige Tabellen können Rollen und Nummern vertauscht extrahieren; solche Ergebnisse sollten vor betrieblicher Nutzung gegen das Quelldokument geprüft werden.

Der Export ist eine Such- und Arbeitshilfe, keine betriebliche Quelle. Maßgeblich bleibt das freigegebene und aktuell gültige Streckenbuch.
