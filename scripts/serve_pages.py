#!/usr/bin/env python3
"""Serve the built web application without browser caching during development."""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIRECTORY = ROOT / "dist" / "pages"


class NoCacheRequestHandler(SimpleHTTPRequestHandler):
    """Static file handler that always asks browsers to fetch current assets."""

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the local GitHub Pages build")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    args = parser.parse_args()

    handler = partial(NoCacheRequestHandler, directory=str(args.directory.resolve()))
    server = ThreadingHTTPServer(("0.0.0.0", args.port), handler)
    print(f"Serving {args.directory.resolve()} at http://localhost:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
