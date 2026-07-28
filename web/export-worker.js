"use strict";

const PYODIDE_VERSION = "0.27.7";
const PYODIDE_BASE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
const OUTPUT_MIME_TYPES = {
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  ods: "application/vnd.oasis.opendocument.spreadsheet",
  csv: "text/csv;charset=utf-8",
};
const ODFPY_ARCHIVE_URL =
  "https://files.pythonhosted.org/packages/97/73/8ade73f6749177003f7ce3304f524774adda96e6aaab30ea79fd8fda7934/odfpy-1.4.1.tar.gz";
const ODFPY_SHA256 = "db766a6e59c5103212f3cc92ec8dd50a0f3a02790233ed0b52148b70d3c438ec";

let enginePromise;

const sendStatus = (jobId, title, detail) => {
  self.postMessage({ type: "status", jobId, title, detail });
};

const initializeEngine = async (jobId) => {
  sendStatus(
    jobId,
    "Browser-Engine wird geladen …",
    "Python/WebAssembly und die Export-Komponenten werden einmalig geladen."
  );
  importScripts(`${PYODIDE_BASE_URL}pyodide.js`);
  const pyodide = await loadPyodide({ indexURL: PYODIDE_BASE_URL });
  await pyodide.loadPackage("micropip");
  await pyodide.runPythonAsync(`
import micropip
await micropip.install([
    "pypdf==6.14.2",
    "openpyxl==3.1.5",
    "et-xmlfile==2.0.0",
    "defusedxml==0.7.1",
])
`);

  // odfpy 1.4.1 is published as a source archive rather than a wheel. It is
  // pure Python, so unpack the pinned, integrity-checked source for importing.
  const odfResponse = await fetch(ODFPY_ARCHIVE_URL, { cache: "force-cache" });
  if (!odfResponse.ok) {
    throw new Error(`ODS-Komponente konnte nicht geladen werden (HTTP ${odfResponse.status}).`);
  }
  const odfArchive = await odfResponse.arrayBuffer();
  const odfArchivePath = "/tmp/odfpy-1.4.1.tar.gz";
  pyodide.FS.writeFile(odfArchivePath, new Uint8Array(odfArchive));
  pyodide.globals.set("odf_archive_path", odfArchivePath);
  const odfDigest = pyodide.runPython(`
import hashlib
from pathlib import Path
hashlib.sha256(Path(odf_archive_path).read_bytes()).hexdigest()
`);
  pyodide.globals.delete("odf_archive_path");
  pyodide.FS.unlink(odfArchivePath);
  if (odfDigest !== ODFPY_SHA256) {
    throw new Error("Integritätsprüfung der ODS-Komponente fehlgeschlagen.");
  }
  pyodide.unpackArchive(odfArchive, "gztar", { extractDir: "/tmp/vendor" });

  const parserResponse = await fetch("./streckenbuch_export.py", { cache: "no-cache" });
  if (!parserResponse.ok) {
    throw new Error(`Parser konnte nicht geladen werden (HTTP ${parserResponse.status}).`);
  }
  pyodide.FS.writeFile("/tmp/streckenbuch_export.py", await parserResponse.text(), {
    encoding: "utf8",
  });
  await pyodide.runPythonAsync(`
import sys
for path in ("/tmp", "/tmp/vendor/odfpy-1.4.1"):
    if path not in sys.path:
        sys.path.insert(0, path)
import streckenbuch_export
`);
  return pyodide;
};

const getEngine = (jobId) => {
  if (!enginePromise) {
    enginePromise = initializeEngine(jobId).catch((error) => {
      enginePromise = undefined;
      throw error;
    });
  }
  return enginePromise;
};

const safeStem = (fileName) => {
  const withoutExtension = fileName.replace(/\.pdf$/i, "");
  const sanitized = withoutExtension.replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_").trim();
  return sanitized || "streckenbuch";
};

const friendlyError = (error) => {
  const message = error instanceof Error ? error.message : String(error);
  if (/password|encrypted|decrypt/i.test(message)) {
    return "Die PDF ist verschlüsselt oder passwortgeschützt und kann im Browser nicht gelesen werden.";
  }
  if (/memory|out of bounds|allocation/i.test(message)) {
    return "Für diese PDF reicht der verfügbare Browser-Speicher nicht aus. Bitte verwenden Sie die Desktop-Version.";
  }
  if (/fetch|network|load failed|failed to load/i.test(message)) {
    return "Die Browser-Komponenten konnten nicht geladen werden. Prüfen Sie die Internetverbindung und versuchen Sie es erneut.";
  }
  return `Die PDF konnte nicht verarbeitet werden: ${message}`;
};

const runExport = async ({ jobId, fileName, format, minConfidence, buffer }) => {
  const supportedFormats = new Set(["xlsx", "ods", "csv", "all"]);
  if (!supportedFormats.has(format)) throw new Error("Unbekanntes Ausgabeformat.");
  if (!Number.isFinite(minConfidence) || minConfidence < 0 || minConfidence > 1) {
    throw new Error("Die Mindestkonfidenz muss zwischen 0 und 1 liegen.");
  }

  const pyodide = await getEngine(jobId);
  sendStatus(
    jobId,
    "PDF wird analysiert …",
    "Seiten, Betriebsstellen und Rufnummern werden lokal ausgewertet. Dies kann einige Minuten dauern."
  );

  const inputPath = "/tmp/browser-input.pdf";
  const outputStem = "/tmp/browser-export";
  pyodide.FS.writeFile(inputPath, new Uint8Array(buffer));
  pyodide.globals.set("web_input_path", inputPath);
  pyodide.globals.set("web_output_stem", outputStem);
  pyodide.globals.set("web_format", format);
  pyodide.globals.set("web_min_confidence", minConfidence);
  pyodide.globals.set("web_source_name", fileName);

  let summary;
  try {
    const summaryJson = await pyodide.runPythonAsync(`
import json
from pathlib import Path
from streckenbuch_export import (
    deduplicate_for_export,
    extract_pdf,
    write_csv,
    write_ods,
    write_xlsx,
)

_input = Path(web_input_path)
_output = Path(web_output_stem)
_records, _stations, _total_pages = extract_pdf(_input, workers=1)
_records = [record for record in _records if record.confidence >= web_min_confidence]
_before_deduplication = len(_records)
_records = deduplicate_for_export(_records)
_duplicates_removed = _before_deduplication - len(_records)
_source = Path(web_source_name)

if web_format in {"xlsx", "all"}:
    write_xlsx(
        _records,
        _stations,
        _output.with_suffix(".xlsx"),
        source_pdf=_source,
        total_pages=_total_pages,
        duplicates_removed=_duplicates_removed,
    )
if web_format in {"ods", "all"}:
    write_ods(
        _records,
        _stations,
        _output.with_suffix(".ods"),
        source_pdf=_source,
        total_pages=_total_pages,
        duplicates_removed=_duplicates_removed,
    )
if web_format in {"csv", "all"}:
    write_csv(_records, _output.with_suffix(".csv"))

json.dumps({
    "contacts": len(_records),
    "stations": len(_stations),
    "duplicatesRemoved": _duplicates_removed,
    "totalPages": _total_pages,
})
`);
    summary = JSON.parse(summaryJson);

    sendStatus(
      jobId,
      "Tabellen werden erstellt …",
      "Die Ergebnisse werden als lokale Download-Dateien verpackt."
    );

    const extensions = format === "all" ? ["xlsx", "ods", "csv"] : [format];
    const stem = `${safeStem(fileName)}_rufnummern`;
    const files = extensions.map((extension) => {
      const bytes = pyodide.FS.readFile(`${outputStem}.${extension}`);
      const copy = bytes.slice().buffer;
      return {
        name: `${stem}.${extension}`,
        type: OUTPUT_MIME_TYPES[extension],
        buffer: copy,
      };
    });

    self.postMessage(
      { type: "complete", jobId, summary, files },
      files.map((file) => file.buffer)
    );
  } finally {
    [inputPath, `${outputStem}.xlsx`, `${outputStem}.ods`, `${outputStem}.csv`].forEach((path) => {
      try {
        pyodide.FS.unlink(path);
      } catch (_error) {
        // A format that was not selected has no output file.
      }
    });
    [
      "web_input_path",
      "web_output_stem",
      "web_format",
      "web_min_confidence",
      "web_source_name",
    ].forEach((name) => pyodide.globals.delete(name));
  }
};

self.addEventListener("message", async ({ data }) => {
  if (data.type !== "export") return;
  try {
    await runExport(data);
  } catch (error) {
    self.postMessage({ type: "error", jobId: data.jobId, message: friendlyError(error) });
  }
});
