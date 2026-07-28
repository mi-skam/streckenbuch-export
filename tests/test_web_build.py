from html.parser import HTMLParser
from pathlib import Path

from scripts.build_pages import build_pages


class LocalAssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.assets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        attribute = "href" if tag == "link" else "src" if tag == "script" else None
        if attribute and values.get(attribute, "").startswith("./"):
            path = values[attribute][2:].partition("?")[0]
            self.assets.append(path)


def test_pages_build_contains_web_app_and_production_parser(tmp_path):
    output = build_pages(tmp_path / "pages")

    expected = {
        ".nojekyll",
        "app.js",
        "export-worker.js",
        "index.html",
        "streckenbuch_export.py",
        "styles.css",
    }
    assert expected <= {path.name for path in output.iterdir()}
    assert (output / "streckenbuch_export.py").read_bytes() == Path(
        "streckenbuch_export.py"
    ).read_bytes()


def test_index_local_assets_exist_in_built_artifact(tmp_path):
    output = build_pages(tmp_path / "pages")
    parser = LocalAssetParser()
    parser.feed((output / "index.html").read_text(encoding="utf-8"))

    assert parser.assets
    assert all((output / asset).is_file() for asset in parser.assets)


def test_worker_uses_pinned_pyodide_and_local_parser():
    worker = Path("web/export-worker.js").read_text(encoding="utf-8")

    assert 'const PYODIDE_VERSION = "0.27.7"' in worker
    assert 'fetch("./streckenbuch_export.py"' in worker
    assert '"pypdf==6.14.2"' in worker
    assert '"openpyxl==3.1.5"' in worker
    assert '"defusedxml==0.7.1"' in worker
    assert "latest" not in worker


def test_worker_integrity_check_does_not_require_a_secure_browser_context():
    worker = Path("web/export-worker.js").read_text(encoding="utf-8")

    assert "crypto.subtle" not in worker
    assert "hashlib.sha256" in worker


def test_browser_assets_are_cache_busted_for_local_retries():
    index = Path("web/index.html").read_text(encoding="utf-8")
    app = Path("web/app.js").read_text(encoding="utf-8")
    server = Path("scripts/serve_pages.py").read_text(encoding="utf-8")

    assert 'app.js?v=' in index
    assert 'export-worker.js?v=' in app
    assert 'Cache-Control", "no-store' in server
