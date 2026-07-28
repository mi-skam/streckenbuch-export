SHELL := /bin/sh

UV ?= uv
PYTHON := $(UV) run python
APP_NAME := StreckenbuchExport
SPEC_FILE := streckenbuch_export.spec

PDF ?=
OUTPUT ?=
FORMAT ?= ods
PAGES ?=
MIN_CONFIDENCE ?= 0
TAG ?= v0.4.0

.PHONY: help setup sync lock test compile check gui cli version \
	export export-ods export-xlsx export-csv export-all \
	web-build web-serve \
	build build-current build-macos build-linux build-windows build-all release \
	clean clean-build distclean

help: ## Show lifecycle and export targets
	@printf '%s\n' \
		'Streckenbuch Export development lifecycle' \
		'' \
		'Setup and checks:' \
		'  make setup                    Install/update locked dependencies' \
		'  make lock                     Refresh uv.lock' \
		'  make test                     Run tests' \
		'  make check                    Compile and run tests' \
		'' \
		'Run:' \
		'  make gui                      Open the desktop application' \
		'  make cli                      Show CLI help' \
		'  make web-build                Build the static GitHub Pages site' \
		'  make web-serve                Build and serve it on localhost:8000' \
		'' \
		'Export:' \
		'  make export-ods  PDF="file.pdf" [OUTPUT="result.ods"]' \
		'  make export-xlsx PDF="file.pdf" [OUTPUT="result.xlsx"]' \
		'  make export-csv  PDF="file.pdf" [OUTPUT="result.csv"]' \
		'  make export-all  PDF="file.pdf" [OUTPUT="result"]' \
		'  Optional: PAGES="15-30,42" MIN_CONFIDENCE=0.8' \
		'' \
		'Executables:' \
		'  make build                    Build for the current operating system' \
		'  make build-macos              Build locally on macOS' \
		'  make build-linux              Build locally on Linux' \
		'  make build-windows            Build locally on Windows/Git Bash' \
		'  make build-all                Trigger an unversioned CI build matrix' \
		'  make release TAG=v0.4.0       Tag and push a downloadable release' \
		'' \
		'Cleanup:' \
		'  make clean                    Remove caches and build artifacts' \
		'  make distclean                Also remove the local virtual environment'

setup sync: ## Synchronize runtime and development dependencies
	$(UV) sync --group dev

lock: ## Refresh dependency lockfile
	$(UV) lock

version: ## Print application version
	$(PYTHON) streckenbuch_export.py --version

test: ## Run unit tests
	$(UV) run pytest

compile: ## Compile-check Python entry points
	$(PYTHON) -m py_compile streckenbuch_export.py streckenbuch_gui.py benchmark_parallel.py

check: compile test ## Run all local checks

gui: setup ## Launch desktop GUI
	$(PYTHON) streckenbuch_gui.py

cli: setup ## Show command-line help
	$(PYTHON) streckenbuch_export.py --help

web-build: ## Build the static GitHub Pages artifact
	python3 scripts/build_pages.py

web-serve: web-build ## Serve the web app locally at http://localhost:8000
	python3 -m http.server 8000 --directory dist/pages

export: setup ## Export PDF using FORMAT (ods/xlsx/csv/all)
	@test -n "$(PDF)" || { echo 'PDF is required, e.g. make export-ods PDF="file.pdf"' >&2; exit 2; }
	$(PYTHON) streckenbuch_export.py "$(PDF)" \
		--format "$(FORMAT)" \
		--min-confidence "$(MIN_CONFIDENCE)" \
		$(if $(strip $(OUTPUT)),--output "$(OUTPUT)",) \
		$(if $(strip $(PAGES)),--pages "$(PAGES)",)

export-ods: FORMAT := ods
export-ods: export ## Export native LibreOffice Calc ODS

export-xlsx: FORMAT := xlsx
export-xlsx: export ## Export Excel XLSX

export-csv: FORMAT := csv
export-csv: export ## Export semicolon-delimited CSV

export-all: FORMAT := all
export-all: export ## Export ODS, XLSX, and CSV

clean-build: ## Remove PyInstaller output
	rm -rf build dist

build build-current: setup clean-build ## Build GUI executable for current OS
	$(UV) run pyinstaller --noconfirm --clean $(SPEC_FILE)
	@printf 'Build output: %s\n' "$(CURDIR)/dist"

build-macos: ## Build executable on macOS
	@test "$$(uname -s)" = Darwin || { echo 'build-macos must run on macOS' >&2; exit 2; }
	$(MAKE) build

build-linux: ## Build executable on Linux
	@test "$$(uname -s)" = Linux || { echo 'build-linux must run on Linux' >&2; exit 2; }
	$(MAKE) build

build-windows: ## Build executable on Windows (Git Bash/MSYS make)
	@test "$(OS)" = Windows_NT || { echo 'build-windows must run on Windows' >&2; exit 2; }
	$(MAKE) build

build-all: ## Trigger unversioned GitHub Actions builds for all platforms
	@command -v gh >/dev/null 2>&1 || { echo 'gh CLI is required for build-all' >&2; exit 2; }
	gh workflow run build-binaries.yml
	@echo 'Build matrix started. Download artifacts from the GitHub Actions run.'

release: check ## Tag current commit; CI builds all platforms and publishes a release
	@test -n "$(TAG)" || { echo 'TAG is required, e.g. make release TAG=v0.4.0' >&2; exit 2; }
	@git diff --quiet && git diff --cached --quiet || { echo 'working tree must be clean' >&2; exit 2; }
	git tag -a "$(TAG)" -m "Streckenbuch Export $(TAG)"
	git push origin "$(TAG)"
	@echo 'Release build started for $(TAG).'

clean: clean-build ## Remove caches and generated Python files
	rm -rf .pytest_cache __pycache__ tests/__pycache__ *.egg-info
	find . -name '*.pyc' -delete

distclean: clean ## Also remove the uv environment
	rm -rf .venv
