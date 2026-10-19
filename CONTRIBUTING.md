# Contributing to id-atlas

Thanks for helping. This project reads identity documents, so a few rules about privacy matter more than
usual. Please read them first.

## The one rule that matters most: no real documents

- **Never** commit a real identity document, a photo of one, or text copied from one. That covers code, tests,
  fixtures, screenshots and commit messages.
- **Never** attach a real document to an issue or a pull request. Redact it, or use a synthetic image.
- Tests build their own fictional documents with Pillow (see `tests/factories.py`). Do the same: made-up
  people, made-up numbers.
- The folder `samples/` and the file `tests/test_specimens.py` are gitignored on purpose. Keep local
  experiments there. Do not remove them from `.gitignore`.

A pull request that contains a real document will be closed and the history cleaned.

## Set up

You need Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/munirahmad9959/id-atlas.git
cd id-atlas
uv sync                  # installs the project and the dev tools
uv run pytest            # about 90 s: most tests run the real OCR on synthetic documents
uv run ruff check . && uv run ruff format --check .
```

To run the service: `uv run id-atlas` (http://127.0.0.1:8000, docs at `/docs`).

## Workflow

1. Look for an issue. For something big, open an issue first so we can agree on the approach.
   Issues labelled `good first issue` and `help wanted` are good starting points.
2. Fork the repository and create a branch from `main`.
3. Make your change. Add or update tests. Keep the change focused: one topic per pull request.
4. Run the tests and `ruff` (above). Both must pass.
5. Open a pull request and fill in the template. Say how you tested it. Give it a title in the commit style
   below (for example `feat(countries): add Pakistani CNIC`): a pull request is squash-merged, and its title
   becomes the one commit message that lands on `main`.
6. CI runs on your pull request: `lint` (ruff and the lockfile), `test` (the full suite) and `docker` (the
   image builds and answers). All three must pass. A first-time contributor's run waits for a maintainer to
   approve it.
7. A maintainer reviews it. Please be ready to adjust.

## Commit style

Conventional commits, as in the history:

```
feat(documents): add Pakistani CNIC parser
fix(mrz): accept a filler character the OCR reads as a letter
test(pipeline): cover a swapped front and back
docs: explain the review reasons
```

Types: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`. The scope is the module or area.

## Code style

- `ruff` sets the style (line length 110). `uv run ruff format .` fixes most things.
- Match the surrounding code: naming, comment density, idiom. Comments say *why*, not *what*.
- Anything that looks wrong should be reported in `review_reasons`, never silently fixed or dropped.

## Adding a document type or a country

A country is **one module** in `src/id_atlas/countries/`. It registers the documents it reads, and the
registry finds it on its own: you edit no other file in `src/`. `src/id_atlas/countries/costa_rica.py` is a
complete, working example. Before you start, open an issue (or take an open one) so we agree on the scope.

### The steps

1. Create `src/id_atlas/countries/<country>.py`.
2. Describe the language of the card with a `Style`: the words that label a field, month names other than
   English, and words that join the parts of a date. Defaults read English months and day-first dates.
3. Write one parser per document. It takes the OCR lines of one side and returns the fields it found.
   Use a `Reader` to find the value that follows a label, and `present()` to drop what was not found.
4. Register each document with a `DocumentSpec`.
5. Use the names in [`documents/fields.py`](src/id_atlas/documents/fields.py). If the document prints
   something with no name there, add the name and its meaning to that file in the same pull request.
6. Add synthetic documents and tests, and add the document to the README table.

### A minimal module

```python
"""Example Republic: the national identity card."""

from ..documents import DocumentSpec, register
from ..documents.text import Reader, Style, present
from ..engine import Line
from ..schemas import Field

STYLE = Style(label_words=r"NAME|GENDER|DATE\s+OF")  # a line with these words is a label, never a value


def parse_id_card(lines: list[Line]) -> dict[str, Field]:
    read = Reader(lines, STYLE)
    return present(
        full_name=read.text_after(r"^NAME"),
        birth_date=read.date_after(r"DATE\s+OF\s+BIRTH"),
        expiry_date=read.date_after(r"DATE\s+OF\s+EXPIRY"),
        document_number=read.text_match(r"\b(\d{5}-\d{7}-\d)\b"),
    )


register(
    DocumentSpec(
        type="example_id",  # snake_case and unique: it is what the API returns
        country="EXA",  # ISO 3166-1 alpha-3
        name="Example national identity card",
        parse=parse_id_card,
        required=("document_number", "full_name", "birth_date", "expiry_date"),
        front_markers=("National Identity Card",),
    )
)
```

### What a `DocumentSpec` says

| Field | Meaning |
|---|---|
| `type`, `country`, `name` | The API name, the issuing country and a name for people. |
| `parse` | Reads the fields of one side. Called once per side; the pipeline merges the sides. |
| `required` | Fields that must be present and confident, or the document goes to review. |
| `front_markers`, `back_markers`, `any_markers` | Words printed on the document. Write them naturally: case, accents, spaces and punctuation are ignored. Front and back markers also tell the sides apart. |
| `two_sided` | A missing back sends the document to review. |
| `verified` | Leave `False` until the parser is proven on enough real documents: it then always asks for review (`template_unverified`). |
| `reconcile` | Optional cross-check against barcodes, such as a number printed and encoded. |

### Guidelines

- Start from the printed labels. A missing label must give a missing field, never another field's value.
- Dates become ISO (`1990-01-12`). An impossible date is reported as invalid, not dropped.
- Use check digits and cross-checks where the document has them (an MRZ, a barcode, a repeated number).
- A parser built on a few documents stays `verified=False`, and the README must say how many real documents
  it was checked against (a number, never the documents themselves).
- Only the text the OCR can read is available. The bundled model reads Latin-script text; Arabic-script text
  such as Urdu comes out as noise, so rely on the Latin text printed on the document.
- Tests: add synthetic pages to `tests/factories.py`, and write `tests/test_<country>.py` that covers the
  classifier, each parser (including a missing label) and one full run of the pipeline. Never use a real
  document.

## Reporting a bug

Run the probe script on your own document. By default it prints only the *shape* of each value (digits as
`9`, letters as `A`), so its output is safe to paste into an issue:

```bash
uv run python scripts/probe_document.py front.jpg back.jpg [document_type]
```

Never paste the output of `--show`, and never attach the image.

## Security issues

Do not open a public issue. See [SECURITY.md](SECURITY.md).

## Licence

By contributing you agree that your contribution is licensed under the [Apache License 2.0](LICENSE), the
same as the project. You keep the copyright on your work.
