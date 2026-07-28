import sys
from types import SimpleNamespace

import pytest

import benchmark_parallel
from benchmark_parallel import extract_texts, parse_texts, split_chunks


def test_split_chunks_balances_ordered_values_without_empty_chunks():
    assert split_chunks(list(range(10)), 3) == [
        [0, 1, 2, 3],
        [4, 5, 6],
        [7, 8, 9],
    ]
    assert split_chunks([1, 2, 3], 10) == [[1], [2], [3]]
    assert split_chunks([1, 2, 3], 0) == [[1, 2, 3]]


@pytest.mark.parametrize("workers", [1, 3])
def test_extract_texts_returns_pdf_page_order_without_real_multiprocessing(
    monkeypatch, tmp_path, workers
):
    submitted_chunks = []

    def fake_extract_chunk(pdf_path, page_indexes):
        submitted_chunks.append(list(page_indexes))
        chunk = list(page_indexes)
        if workers > 1:
            chunk = list(reversed(chunk))
        return [(page_index, f"page {page_index}") for page_index in chunk]

    class FakeFuture:
        def __init__(self, result):
            self._result = result

        def result(self):
            return self._result

    class FakeExecutor:
        def __init__(self, *, max_workers):
            self.max_workers = max_workers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, func, pdf_path, chunk):
            return FakeFuture(func(pdf_path, chunk))

    monkeypatch.setattr(benchmark_parallel, "extract_chunk", fake_extract_chunk)
    monkeypatch.setattr(benchmark_parallel, "ProcessPoolExecutor", FakeExecutor)

    extracted = extract_texts(tmp_path / "dummy.pdf", [0, 1, 2, 3, 4], workers)

    assert extracted == [
        (0, "page 0"),
        (1, "page 1"),
        (2, "page 2"),
        (3, "page 3"),
        (4, "page 4"),
    ]
    if workers == 1:
        assert submitted_chunks == [[0, 1, 2, 3, 4]]
    else:
        assert submitted_chunks == [[0, 1], [2, 3], [4]]


def test_parse_texts_preserves_page_order_and_inherits_context_across_pages():
    first_page = """1 München Hbf - Augsburg
2. Regeln für Betriebsstellen
Bf München Hbf
Fdl Tisch 2 77014302
14
"""
    inherited_context_page = """Deckblatt Streckenverzeichnis
1
Ril 481.0302 2 (4)
Ww: Kurzwahl 1350 Langwahl 77014202
15
"""

    records, stations = parse_texts([(14, first_page), (15, inherited_context_page)])

    assert [(station.pdf_page, station.station_name) for station in stations] == [
        (15, "München Hbf")
    ]
    inherited = next(record for record in records if record.long_number == "77014202")
    assert inherited.pdf_page == 16
    assert inherited.document_page == 15
    assert inherited.route_number == "1"
    assert inherited.station_name == "München Hbf"


def test_benchmark_caps_worker_range_without_real_pdf_or_multiprocessing(monkeypatch, tmp_path):
    class FakePdfReader:
        def __init__(self, pdf_path, strict):
            self.pages = [object()] * 5

    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=FakePdfReader))
    monkeypatch.setattr(benchmark_parallel, "effective_cpu_count", lambda: 3)

    calls = []

    def fake_extract_texts(pdf_path, page_indexes, workers):
        calls.append((tuple(page_indexes), workers))
        return [(page_index, "") for page_index in page_indexes]

    monkeypatch.setattr(benchmark_parallel, "extract_texts", fake_extract_texts)
    monkeypatch.setattr(benchmark_parallel, "parse_texts", lambda extracted: ([], []))
    monkeypatch.setattr(benchmark_parallel, "result_fingerprint", lambda records, stations: "stable")

    ticks = iter(range(20))
    monkeypatch.setattr(benchmark_parallel.time, "perf_counter", lambda: next(ticks))

    assert benchmark_parallel.benchmark(
        tmp_path / "source.pdf", max_workers=10, repeats=1, page_limit=4
    ) == 0

    assert calls == [
        ((0, 1, 2, 3), 1),
        ((0, 1, 2, 3), 2),
        ((0, 1, 2, 3), 3),
    ]


def test_benchmark_caps_workers_by_page_limit(monkeypatch, tmp_path):
    class FakePdfReader:
        def __init__(self, pdf_path, strict):
            self.pages = [object()] * 8

    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=FakePdfReader))
    monkeypatch.setattr(benchmark_parallel, "effective_cpu_count", lambda: 8)

    workers_seen = []
    monkeypatch.setattr(
        benchmark_parallel,
        "extract_texts",
        lambda pdf_path, page_indexes, workers: workers_seen.append(workers) or [],
    )
    monkeypatch.setattr(benchmark_parallel, "parse_texts", lambda extracted: ([], []))
    monkeypatch.setattr(benchmark_parallel, "result_fingerprint", lambda records, stations: "stable")

    ticks = iter(range(20))
    monkeypatch.setattr(benchmark_parallel.time, "perf_counter", lambda: next(ticks))

    benchmark_parallel.benchmark(tmp_path / "source.pdf", max_workers=99, repeats=1, page_limit=2)

    assert workers_seen == [1, 2]
