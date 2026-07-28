#!/usr/bin/env python3
"""Create the static GitHub Pages artifact.

The web worker imports the production parser at runtime. Copying that module
into the artifact avoids maintaining a second parser implementation.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_SOURCE = ROOT / "web"
PARSER_SOURCE = ROOT / "streckenbuch_export.py"
DEFAULT_OUTPUT = ROOT / "dist" / "pages"
REQUIRED_WEB_FILES = (
    ".nojekyll",
    "app.js",
    "export-worker.js",
    "index.html",
    "styles.css",
)


def build_pages(output: Path = DEFAULT_OUTPUT) -> Path:
    """Build a self-contained static artifact and return its path."""
    missing = [name for name in REQUIRED_WEB_FILES if not (WEB_SOURCE / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing web source files: {', '.join(missing)}")
    if not PARSER_SOURCE.is_file():
        raise FileNotFoundError(f"Missing parser source: {PARSER_SOURCE}")

    output = output.resolve()
    if output == ROOT or ROOT in output.parents and output == WEB_SOURCE:
        raise ValueError("Refusing to overwrite a source directory")
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(WEB_SOURCE, output)
    shutil.copy2(PARSER_SOURCE, output / PARSER_SOURCE.name)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the GitHub Pages artifact")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = build_pages(args.output)
    print(f"GitHub Pages artifact: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
