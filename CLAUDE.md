# id-atlas

Lightweight, self-hosted OCR for identity documents. Python 3.12, FastAPI, RapidOCR (ONNX, CPU only).
Costa Rica is the only country module today; everything else is country-neutral. Output is a hint for a
human reviewer, not a verdict.

## Commands

```bash
uv sync                                  # install, including dev tools
uv run pytest                            # about 90 s: most tests run the real OCR on synthetic documents
uv run ruff check . && uv run ruff format --check .
uv run id-atlas                          # serve http://127.0.0.1:8000, docs at /docs
uv run python scripts/probe_document.py front.jpg [back.jpg] [document_type]   # hides values by default
```

## Layout (`src/id_atlas/`)

- `engine.py` OCR and rotation recovery. `mrz.py` ICAO 9303 MRZ (TD1, TD2, TD3) with check digits.
- `documents/` the registry (`DocumentSpec`, `register`), `classify`, the shared text/date helpers
  (`Style`, `Reader`) and `fields.py`, the only list of allowed field names.
- `countries/` one module per country; every module here is imported automatically. Copy
  `costa_rica.py` for a new one. Adding a country must not require editing anything outside this folder
  (plus tests, `fields.py` if a new field name is needed, and the README table).
- `pipeline.py` merges both sides and applies review rules. `api.py`, `config.py`, `schemas.py`, `cli.py`.

## Rules

- **Never** put a real identity document, a photo of one or text copied from one in code, tests, fixtures,
  logs, commit messages or issues. Tests build fictional documents (`tests/factories.py`). `samples/` and
  `tests/test_specimens.py` are gitignored on purpose.
- Parsers may only produce names from `documents/fields.py`. A missing label gives a missing field, never
  another field's value. Anything doubtful goes into `review_reasons`; nothing is silently fixed or dropped.
- Shared code (`documents/`, `pipeline.py`, `mrz.py`) stays free of any one country's or language's words;
  those belong in the country module's `Style` and markers.
- A parser not yet proven on enough real documents stays `verified=False` (it then always asks for review).
- Images and extracted values are never written to disk or logged.
- Conventional commits: `feat(scope):`, `fix(scope):`, `refactor(scope):`, `test(scope):`, `docs:`,
  `chore:`. Comments say why, not what. Ruff line length is 110.
- Add or update tests with every behaviour change, and keep `README.md` and `CHANGELOG.md` true to the code.
- CI (`.github/workflows/ci.yml`) runs `lint`, `test` and `docker`; they are the required checks on `main`, so
  keep those job names, and never add path filters to the workflow.
