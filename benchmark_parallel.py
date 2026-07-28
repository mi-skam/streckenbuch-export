#!/usr/bin/env python3
"""Benchmark ordered PDF extraction with 1..effective CPU workers.

Only text extraction is parallel. Parsing stays in PDF-page order because a
page inherits route, station, and rule context from the preceding page.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import statistics
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Sequence

from streckenbuch_export import ContactRecord, ParseContext, StationRecord, parse_page


def effective_cpu_count() -> int:
    """Return the CPUs available to this process, with portable fallbacks."""
    process_cpu_count = getattr(os, "process_cpu_count", None)
    if process_cpu_count is not None:
        count = process_cpu_count()
        if count:
            return count
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        return os.cpu_count() or 1


def split_chunks(values: Sequence[int], chunk_count: int) -> list[list[int]]:
    """Split ordered values into at most chunk_count non-empty chunks."""
    chunk_count = max(1, min(chunk_count, len(values)))
    quotient, remainder = divmod(len(values), chunk_count)
    chunks: list[list[int]] = []
    start = 0
    for index in range(chunk_count):
        size = quotient + (index < remainder)
        chunks.append(list(values[start : start + size]))
        start += size
    return chunks


def extract_chunk(pdf_path: str, page_indexes: Sequence[int]) -> list[tuple[int, str]]:
    """Open a reader once per worker and extract one contiguous page chunk."""
    from pypdf import PdfReader

    reader = PdfReader(pdf_path, strict=False)
    extracted: list[tuple[int, str]] = []
    for page_index in page_indexes:
        page = reader.pages[page_index]
        try:
            text = page.extract_text(extraction_mode="layout") or ""
        except (TypeError, ValueError):
            text = page.extract_text() or ""
        extracted.append((page_index, text))
    return extracted


def extract_texts(
    pdf_path: Path, page_indexes: Sequence[int], workers: int
) -> list[tuple[int, str]]:
    """Extract text in parallel and restore deterministic PDF-page order."""
    chunks = split_chunks(page_indexes, workers)
    if workers == 1:
        return extract_chunk(str(pdf_path), chunks[0])

    extracted: list[tuple[int, str]] = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(extract_chunk, str(pdf_path), chunk) for chunk in chunks]
        for future in futures:
            extracted.extend(future.result())
    extracted.sort(key=lambda item: item[0])
    return extracted


def parse_texts(
    extracted: Sequence[tuple[int, str]],
) -> tuple[list[ContactRecord], list[StationRecord]]:
    """Parse extracted text sequentially to preserve inherited page context."""
    context = ParseContext()
    records: list[ContactRecord] = []
    stations: list[StationRecord] = []
    for page_index, text in extracted:
        result = parse_page(text, pdf_page=page_index + 1, previous_context=context)
        context = result.context
        records.extend(result.records)
        stations.extend(result.stations)
    return records, stations


def result_fingerprint(
    records: Sequence[ContactRecord], stations: Sequence[StationRecord]
) -> str:
    digest = hashlib.sha256()
    for value in (*records, *stations):
        digest.update(repr(value).encode("utf-8"))
    return digest.hexdigest()[:12]


def benchmark(
    pdf_path: Path,
    *,
    max_workers: int | None = None,
    repeats: int = 3,
    page_limit: int | None = None,
) -> int:
    from pypdf import PdfReader

    total_pages = len(PdfReader(str(pdf_path), strict=False).pages)
    tested_pages = min(total_pages, page_limit) if page_limit else total_pages
    page_indexes = list(range(tested_pages))
    available_cpus = effective_cpu_count()
    worker_limit = min(max_workers or available_cpus, available_cpus, tested_pages)
    if worker_limit < 1:
        raise ValueError("No pages available to benchmark")

    print(f"PDF: {pdf_path}")
    print(
        f"Pages: {tested_pages}/{total_pages}; effective CPUs: {available_cpus}; "
        f"workers tested: 1..{worker_limit}; repeats: {repeats}"
    )
    print("workers  median_s  speedup  efficiency  result")

    baseline: float | None = None
    expected_fingerprint: str | None = None
    for workers in range(1, worker_limit + 1):
        durations: list[float] = []
        fingerprint = ""
        for _ in range(repeats):
            started = time.perf_counter()
            extracted = extract_texts(pdf_path, page_indexes, workers)
            records, stations = parse_texts(extracted)
            durations.append(time.perf_counter() - started)
            fingerprint = result_fingerprint(records, stations)
        median = statistics.median(durations)
        if baseline is None:
            baseline = median
            expected_fingerprint = fingerprint
        if fingerprint != expected_fingerprint:
            raise RuntimeError(
                f"Result changed at {workers} workers: "
                f"{fingerprint} != {expected_fingerprint}"
            )
        speedup = baseline / median
        efficiency = speedup / workers
        print(
            f"{workers:>7}  {median:>8.3f}  {speedup:>7.2f}x  "
            f"{efficiency:>9.1%}  {fingerprint}"
        )
    return 0


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="Representative PDF to benchmark")
    parser.add_argument(
        "--max-workers",
        type=int,
        help="Upper worker limit (default: effective CPU count)",
    )
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--pages", type=int, help="Benchmark only the first N PDF pages"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    if not args.pdf.is_file():
        raise SystemExit(f"PDF not found: {args.pdf}")
    if args.max_workers is not None and args.max_workers < 1:
        raise SystemExit("--max-workers must be at least 1")
    if args.repeats < 1:
        raise SystemExit("--repeats must be at least 1")
    if args.pages is not None and args.pages < 1:
        raise SystemExit("--pages must be at least 1")
    return benchmark(
        args.pdf.resolve(),
        max_workers=args.max_workers,
        repeats=args.repeats,
        page_limit=args.pages,
    )


if __name__ == "__main__":
    raise SystemExit(main())
