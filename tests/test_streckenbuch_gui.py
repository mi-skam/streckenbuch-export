from pathlib import Path

import pytest

import streckenbuch_gui as gui
from streckenbuch_export import PROGRAM_NAME, PROGRAM_VERSION


def test_gui_uses_shared_name_and_version():
    assert gui.APP_NAME == PROGRAM_NAME
    assert gui.APP_VERSION == PROGRAM_VERSION


def test_run_export_all_formats_without_tk(tmp_path, monkeypatch):
    pdf_path = tmp_path / "Mein Streckenbuch.pdf"
    pdf_path.write_bytes(b"%PDF-test")
    output_directory = tmp_path / "export"
    first_record = object()
    duplicate_record = object()
    station = object()
    calls = []
    statuses = []

    monkeypatch.setattr(
        gui,
        "extract_pdf",
        lambda path: ([first_record, duplicate_record], [station], 777),
    )
    monkeypatch.setattr(gui, "deduplicate_for_export", lambda records: [records[0]])

    def capture_xlsx(records, stations, path, **metadata):
        calls.append(("xlsx", records, stations, path, metadata))

    def capture_ods(records, stations, path, **metadata):
        calls.append(("ods", records, stations, path, metadata))

    def capture_csv(records, path):
        calls.append(("csv", records, path))

    monkeypatch.setattr(gui, "write_xlsx", capture_xlsx)
    monkeypatch.setattr(gui, "write_ods", capture_ods)
    monkeypatch.setattr(gui, "write_csv", capture_csv)

    result = gui.run_export(
        pdf_path, output_directory, "all", status=statuses.append
    )

    assert result == gui.ExportResult(
        output_files=(
            output_directory / "Mein Streckenbuch_rufnummern.xlsx",
            output_directory / "Mein Streckenbuch_rufnummern.ods",
            output_directory / "Mein Streckenbuch_rufnummern.csv",
        ),
        contact_count=1,
        station_count=1,
        duplicates_removed=1,
        total_pages=777,
    )
    assert [call[0] for call in calls] == ["xlsx", "ods", "csv"]
    assert calls[0][4] == {
        "source_pdf": pdf_path,
        "total_pages": 777,
        "duplicates_removed": 1,
    }
    assert calls[1][4] == calls[0][4]
    assert statuses == [
        "PDF wird analysiert …",
        "Fundstellen werden bereinigt …",
        "XLSX-Datei wird geschrieben …",
        "ODS-Datei wird geschrieben …",
        "CSV-Datei wird geschrieben …",
    ]


def test_run_export_turns_core_system_exit_into_gui_error(tmp_path, monkeypatch):
    pdf_path = tmp_path / "input.pdf"
    pdf_path.touch()

    def fail(_path):
        raise SystemExit("pypdf fehlt")

    monkeypatch.setattr(gui, "extract_pdf", fail)

    with pytest.raises(gui.ExportError, match="pypdf fehlt"):
        gui.run_export(pdf_path, tmp_path, "xlsx")


def test_run_export_rejects_non_pdf_before_calling_core(tmp_path, monkeypatch):
    input_path = tmp_path / "input.txt"
    input_path.touch()
    monkeypatch.setattr(
        gui,
        "extract_pdf",
        lambda _path: pytest.fail("extract_pdf must not be called"),
    )

    with pytest.raises(gui.ExportError, match="PDF-Datei"):
        gui.run_export(input_path, tmp_path, "csv")


def test_dropped_path_decodes_file_url():
    assert gui.dropped_path("file:///tmp/Mein%20Streckenbuch.pdf") == Path(
        "/tmp/Mein Streckenbuch.pdf"
    )
