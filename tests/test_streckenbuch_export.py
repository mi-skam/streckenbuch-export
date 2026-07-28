from pathlib import Path
import tomllib
import zipfile

from streckenbuch_export import (
    PROGRAM_VERSION,
    ContactRecord,
    StationRecord,
    deduplicate_for_export,
    extract_pdf,
    output_paths,
    parse_page,
    parse_page_selection,
    recommended_worker_count,
    split_page_chunks,
    station_from_line,
    write_ods,
)


def test_program_version_matches_project_metadata():
    metadata = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    assert PROGRAM_VERSION == metadata["project"]["version"]


def test_parses_station_heading_and_direct_numbers():
    text = """Deckblatt Streckenverzeichnis
1
1 München Hbf - Augsburg
2. Regeln für Betriebsstellen
Bf München Hbf
BÜ 77014202
Fdl Tisch 2 (Gleis 7 - 18) 77014302
Ril 481.0302 2 (4)
Rufnummern der Weichenwärter
Ww MH Fdl Mf-Tisch 2: Kurzwahl: 1352, Langwahl 77014302
14
"""
    result = parse_page(text, pdf_page=15)

    assert result.context.route_number == "1"
    assert result.context.station_name == "München Hbf"
    assert any(r.long_number == "77014302" and r.short_number == "1352" for r in result.records)
    assert any(r.position == "Fdl Tisch 2 (Gleis 7 - 18)" for r in result.records)
    assert all(r.document_page == 14 for r in result.records)


def test_parses_functional_and_spaced_long_number():
    text = """3 Regensburg Hbf - Hof Hbf
2. Regeln für Betriebsstellen
Bf Nabburg
Ril 481.0205 7
Zugvorbereitungsmeldung über GSM-R (999010004).
Ril 481.0302 2 (5)
Ww Stw 2 (Fdl): Kurzwahl: 1352 Langwahl: 776 438 02
44
"""
    result = parse_page(text, pdf_page=45)

    assert any(r.functional_number == "999010004" for r in result.records)
    assert any(r.short_number == "1352" and r.long_number == "77643802" for r in result.records)


def test_parses_table_row():
    text = """25 La Mitte
2. Regeln für Betriebsstellen
Bf Jossa
Ril 481.0302 2 (5)
Stelle Kurzwahl Langwahl Zuständigkeitsbereich
Jossa 1350 77032902 Gesamter Bf
243
"""
    result = parse_page(text, pdf_page=244)

    row = next(r for r in result.records if r.long_number == "77032902")
    assert row.short_number == "1350"
    assert row.position == "Jossa"
    assert row.station_name == "Jossa"


def test_inherits_route_and_station_across_page():
    previous = parse_page(
        """1 München Hbf - Augsburg
2. Regeln für Betriebsstellen
Bf München Hbf
Fdl Tisch 2 77014302
14
""",
        pdf_page=15,
    ).context
    result = parse_page(
        """Deckblatt Streckenverzeichnis
1
Ril 481.0302 2 (4)
Ww: Kurzwahl 1350 Langwahl 77014202
15
""",
        pdf_page=16,
        previous_context=previous,
    )

    row = next(r for r in result.records if r.long_number == "77014202")
    assert row.route_number == "1"
    assert row.station_name == "München Hbf"


def test_station_names_are_canonicalized_and_table_lines_rejected():
    assert station_from_line("Bf Olching (özF Mering - BZ München) 77022302") == (
        "Bf",
        "Olching",
    )
    assert station_from_line("Bft Augsburg Rbf Mitte Fdl Süd 77020802") == (
        "Bft",
        "Augsburg Rbf Mitte",
    )
    assert station_from_line("Bft MHB BÜ Gleise 788 und 789 10 km/h") is None


def test_export_deduplication_ignores_provenance_but_preserves_contacts():
    first = ContactRecord(
        route_number="1",
        station_type="Bf",
        station_name="München Hbf",
        position="Fdl Tisch 2",
        long_number="77014302",
        pdf_page=15,
        source_text="erste Fundstelle",
    )
    duplicate = ContactRecord(
        route_number="1",
        station_type="BF",
        station_name=" München Hbf ",
        position="fdl tisch 2",
        long_number="77014302",
        pdf_page=19,
        source_text="wiederholte Fundstelle",
    )
    other_contact = ContactRecord(
        route_number="1",
        station_type="Bf",
        station_name="München Hbf",
        position="Fdl Tisch 3",
        long_number="77014502",
        pdf_page=15,
    )

    result = deduplicate_for_export([first, duplicate, other_contact])

    assert result == [first, other_contact]


def test_native_ods_contains_calc_filter_ranges_and_text_numbers(tmp_path):
    record = ContactRecord(
        route_number="1",
        station_type="Bf",
        station_name="München Hbf",
        position="Fdl Tisch 2",
        short_number="1352",
        long_number="77014302",
        pdf_page=15,
        document_page=14,
        confidence=0.96,
    )
    station = StationRecord("1", "München - Augsburg", "Bf", "München Hbf", 15, 14)
    output = tmp_path / "export.ods"

    write_ods(
        [record],
        [station],
        output,
        source_pdf=tmp_path / "source.pdf",
        total_pages=777,
        duplicates_removed=2,
    )

    with zipfile.ZipFile(output) as archive:
        content = archive.read("content.xml").decode()
    assert 'table:name="KontakteFilter"' in content
    assert 'table:target-range-address="Kontakte.A1:Kontakte.R2"' in content
    assert 'table:contains-header="true"' in content
    assert 'table:display-filter-buttons="true"' in content
    assert (
        'office:value-type="string" table:style-name="BodyCell">'
        "<text:p>77014302</text:p>"
    ) in content
    assert "1352" in content


def test_extract_pdf_accepts_blank_pages_without_contents_stream(tmp_path):
    from pypdf import PdfWriter

    pdf = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(pdf)

    records, stations, total_pages = extract_pdf(pdf, workers=1)

    assert records == []
    assert stations == []
    assert total_pages == 1


def test_output_paths_support_native_and_all_formats(tmp_path):
    pdf = tmp_path / "source.pdf"
    assert output_paths(pdf, None, "ods") == (
        None,
        tmp_path / "source_rufnummern.ods",
        None,
    )
    assert output_paths(pdf, tmp_path / "result.ods", "all") == (
        tmp_path / "result.xlsx",
        tmp_path / "result.ods",
        tmp_path / "result.csv",
    )


def test_page_selection():
    assert parse_page_selection("1,3-5,8", 10) == [0, 2, 3, 4, 7]


def test_page_chunks_are_balanced_and_ordered():
    assert split_page_chunks(list(range(10)), 3) == [
        [0, 1, 2, 3],
        [4, 5, 6],
        [7, 8, 9],
    ]


def test_recommended_workers_adapt_to_cpus_pages_and_memory_cap(monkeypatch):
    monkeypatch.setattr("streckenbuch_export.effective_cpu_count", lambda: 64)

    assert recommended_worker_count(9) == 1
    assert recommended_worker_count(40) == 4
    assert recommended_worker_count(320) == 8
    assert recommended_worker_count(320, requested=100) == 64
    assert recommended_worker_count(3, requested=8) == 3
