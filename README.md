# id-atlas

[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](pyproject.toml)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230.svg)](https://docs.astral.sh/ruff/)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

Lightweight, self-hosted OCR for identity documents. Costa Rica is supported today, and every other
country is one small module away: see [Adding a country](CONTRIBUTING.md#adding-a-document-type-or-a-country).

Upload the front and back photos of an ID card, driver's license or passport; get back one structured
result with every field, a confidence per field, and the reasons a human should double-check it. It runs
on a CPU, needs no GPU and no cloud service, and your images never leave your server.

> **Early stage.** The parsers were built and checked against a handful of real cards and specimens.
> Treat the output as a hint for a human reviewer, not as a verdict. This is not a certified KYC or
> fraud-detection product. See [Limitations](#limitations).

## What it reads

| Document | Sides | Status |
|---|---|---|
| Passport, and any ICAO 9303 document with a machine-readable zone (TD1, TD2 and TD3) | one page | Reads the MRZ and verifies every check digit. Works for any country. |
| Costa Rican cédula de identidad | front and back | Number, names, surnames, birth and expiry dates. Checked on one real card. |
| Costa Rican driver's license | front and back | Number, category, issue, birth and expiry dates, cross-checked against its PDF417 barcode. Checked on one real card. |
| DIMEX (residence card) | front and back | Provisional: the document number only. No real sample seen yet. |

Dates are normalised to ISO (`1990-01-12`) from the formats printed on the cards, such as `12/01/1990`,
`12-01-1990`, `12 01 1990`, `12 JAN 1990` and, on Costa Rican cards, `12 ENE 1990`.

Ask the running service which documents it knows with `GET /v1/documents`.

## How it works

```
front + back photos
   |
   v  decode, apply EXIF rotation, shrink for OCR (and keep a larger copy for barcodes)
   v  OCR (RapidOCR / PP-OCRv6 small, ONNX Runtime, CPU); re-orient sideways or upside-down photos
   v  per side: MRZ parse + check digits, barcode decode, document type, which side it is
   v  merge both sides into ONE result (front wins ties; a valid value beats an unreadable one)
   v  cross-checks: sides match, not swapped, not the same photo twice, values agree, barcode agrees
   v
fields + confidences + needs_review + review_reasons
```

Anything that looks wrong is reported in `review_reasons` instead of being silently fixed or dropped.

## Quick start

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run id-atlas            # serves http://127.0.0.1:8000 (interactive docs at /docs)
```

Read a document from its two sides:

```bash
curl -F front=@front.jpg -F back=@back.jpg http://127.0.0.1:8000/v1/extract/document
```

A passport, or any single image:

```bash
curl -F file=@passport.jpg http://127.0.0.1:8000/v1/extract
```

<details>
<summary>Example response (a synthetic cédula with fictional data)</summary>

```json
{
    "document_type": "cedula",
    "country": "CRI",
    "fields": {
        "given_names": {
            "value": "ANA MARIA",
            "raw": "ANA MARIA",
            "confidence": 0.998,
            "side": "front"
        },
        "surname": {
            "value": "PRUEBA",
            "raw": "PRUEBA",
            "confidence": 0.999,
            "side": "front"
        },
        "second_surname": {
            "value": "MUESTRA",
            "raw": "MUESTRA",
            "confidence": 0.986,
            "side": "front"
        },
        "birth_date": {
            "value": "1990-01-12",
            "raw": "12/01/1990",
            "confidence": 0.992,
            "side": "front"
        },
        "expiry_date": {
            "value": "2030-03-05",
            "raw": "05/03/2030",
            "confidence": 0.992,
            "side": "front"
        },
        "document_number": {
            "value": "199999999",
            "raw": "1 9999 9999",
            "confidence": 0.964,
            "side": "front"
        }
    },
    "mrz": null,
    "barcodes": [
        "TEST-PAYLOAD-123456"
    ],
    "sides": [
        {
            "side": "front",
            "document_type": "cedula",
            "fields_found": 6
        },
        {
            "side": "back",
            "document_type": "cedula",
            "fields_found": 3
        }
    ],
    "needs_review": false,
    "review_reasons": [],
    "elapsed_ms": 1371
}
```

</details>

On an Intel Mac, `onnxruntime` stopped shipping macOS Intel wheels after 1.23.2, so `pyproject.toml` pins that
version for that platform only.

### Docker

```bash
docker build -t id-atlas .
docker run --rm -p 8000:8000 -e ID_ATLAS_API_KEY=change-me id-atlas
```

The image installs from the frozen lockfile, runs as a non-root user and listens on all interfaces inside
the container. If the container fails to start on your platform, please open an issue with the log.

## API

| Method and path | Purpose |
|---|---|
| `POST /v1/extract/document` | One document: multipart `front` (required), `back` (optional), `document_type` (optional hint). Returns one combined result. |
| `POST /v1/extract` | One image on its own: multipart `file`, optional `document_type`. No front/back checks. |
| `GET /v1/documents` | The document types this service can read: `type`, `country`, `name`, `two_sided`, `verified` and the `required` fields of each. |
| `GET /health` | Liveness. Always open, even when an API key is set. |

`document_type` forces a type instead of detecting it. Use any `type` listed by `GET /v1/documents`
(today `cedula`, `driver_license`, `dimex`, `passport` and `id_mrz`); any other value is a `422`.

Errors: `401` wrong or missing `X-API-Key` (only when a key is configured), `413` an image is over the upload
limit, `422` an image cannot be read (the message names the side, for example `back: not a readable image`) or
a part is missing.

### Field names

Every country uses the same names for the same things, so a client reading documents from several countries
needs no table of exceptions. The names, with their meaning, live in
[`documents/fields.py`](src/id_atlas/documents/fields.py): `document_number`, `national_id_number`,
`given_names`, `surname`, `second_surname`, `full_name`, `father_name`, `sex`, `birth_date`, `issue_date`,
`expiry_date`, `nationality`, `issuing_country` and `license_category`. A document gives either `given_names`
and `surname`, or `full_name` when the card prints the whole name as one string. Names are never split by
guesswork.

### The result

| Field | Meaning |
|---|---|
| `document_type` | A type from `GET /v1/documents` (`id_mrz` is an MRZ document that is not a passport), or `unknown` |
| `country` | The issuing country as an ISO 3166-1 alpha-3 code such as `CRI`: the document type's own, or the one its MRZ states. `null` when unknown |
| `fields` | Keyed by the [field names](#field-names). Each field has `value` (normalised, or `null` if unreadable), `raw` (the text as read), `confidence` (0 to 1) and `side` (which image it came from) |
| `mrz` | The parsed machine-readable zone with the result of every check digit, or `null` |
| `barcodes` | Text of the barcodes decoded from either side |
| `sides` | What each image was recognised as and how many fields it gave |
| `needs_review` | `true` when `review_reasons` is not empty |
| `review_reasons` | Why a person should look at this document (below) |
| `elapsed_ms` | Processing time |

Review reasons:

| Reason | Meaning |
|---|---|
| `unknown_document_type` | Nothing recognised the document |
| `template_unverified` | The reader for this type is not yet validated on enough real documents (license, DIMEX) |
| `missing:<field>`, `invalid:<field>`, `low_confidence:<field>` | A required field is absent, present but not a valid value (such as `00/00/0000`), or read with confidence below the threshold |
| `mrz_checksum_failed` | A machine-readable zone check digit does not match |
| `missing_back_side` | The document has two sides and only one was sent |
| `sides_mismatch` | Front and back look like different documents |
| `sides_possibly_swapped` | The text suggests front and back are the wrong way round |
| `duplicate_sides` | Both images look like the same photo |
| `field_conflict:<field>` | A field printed on both sides has different values |
| `barcode_mismatch:<field>` | The license barcode disagrees with the printed text |

## Configuration

Environment variables, or a `.env` file in the working directory.

| Variable | Default | Purpose |
|---|---|---|
| `ID_ATLAS_HOST` | `127.0.0.1` | Address to listen on. Loopback unless you choose otherwise. |
| `ID_ATLAS_PORT` | `8000` | Port |
| `ID_ATLAS_API_KEY` | unset | When set, extraction routes require this value in the `X-API-Key` header |
| `ID_ATLAS_MAX_UPLOAD_BYTES` | `10485760` | Largest accepted image |
| `ID_ATLAS_MAX_IMAGE_SIDE` | `1600` | Longest side, in pixels, given to the OCR; larger photos are shrunk |
| `ID_ATLAS_BARCODE_MAX_SIDE` | `3000` | Longest side of the copy used for barcodes |
| `ID_ATLAS_ROTATION_RETRY_BELOW` | `0.8` | Mean OCR confidence under which a photo is retried at other rotations |
| `ID_ATLAS_REVIEW_BELOW` | `0.85` | Field confidence under which a document is sent to review |

## Performance and resources

Measured on an Intel Core i9-9980HK laptop (16 threads, 32 GB), CPU only, with synthetic documents:

- **Speed:** about 0.8 to 1 s for a single image and 1.2 to 1.8 s for a two-sided document. A photo that must
  be re-oriented takes longer, roughly 2 to 3 s.
- **Memory:** about **0.8 GB** resident right after startup and **1.4 GB** after a few requests (macOS).
  The service is CPU-only and quick, but it is **not light on memory**: plan for at least 2 GB per instance.
  Reducing this is an open task.
- **Install size:** about 400 MB including the OCR models, which are bundled in the package.
- **Concurrency:** one inference runs at a time (the OCR engine is guarded by a lock). Scale by running more
  instances, not more workers.

These numbers come from one machine and synthetic cards. Real photos and other hardware will differ.

## Privacy and security

- Images and extracted values are processed in memory and are **never written to disk or logged** by this service.
- It listens on loopback by default and has an optional API key. Put it behind your own network controls;
  it is meant to be called by your backend, not by browsers.
- The cédula's printed parents' names, birthplace and electoral address are deliberately **not extracted**.
  The cédula's own barcode is not decoded or relied upon.
- Do not commit real identity documents to this repository, and do not attach them to issues.
  Redact them or use synthetic images; the test suite generates its own documents.
- There is no liveness check, face matching or forgery detection. A passing result does not prove a
  document is genuine.

## Limitations

- Accuracy is unproven beyond the samples above. The cédula and license parsers each rest on one real card.
- Layouts change between issues of a document. A card issued in a different design may not parse.
- Only Costa Rican documents have a country module today (the MRZ documents work for any country). Each
  country is one module in `src/id_atlas/countries/`, so adding one does not touch the rest of the code.
- A very dense or blurry barcode cannot be decoded from an ordinary phone photo, and an unreadable barcode is
  simply skipped.
- Only the Latin-script and Chinese/Japanese text the bundled OCR model knows is read. Arabic-script text
  such as Urdu comes out as noise, so a parser must rely on the Latin text printed on a document. Other
  RapidOCR models exist (Arabic, Cyrillic, Devanagari...) but they are downloaded at run time, which
  would break the no-network promise, so they are not offered yet.
- Two *different* pale pages with little text can be mistaken for the same photo by the duplicate check.

## Development

```bash
uv sync                  # includes the dev tools
uv run pytest            # about 90 s: most tests run the real OCR on synthetic documents
uv run ruff check . && uv run ruff format --check .
```

The tests build fictional documents with Pillow (Spanish labels, made-up people, real PDF417, Code 128 and QR
barcodes), so they run on a fresh clone with no external files.

Two scripts run the same pipeline from the terminal. They hide values by default, so their output is safe to
paste into an issue; `--show` prints the real values to your own terminal only.

```bash
uv run python scripts/probe_document.py front.jpg back.jpg [document_type] [--show]   # any type from GET /v1/documents
uv run python scripts/probe_barcode.py photo.jpg       # which strategy, if any, decodes a barcode
```

Source layout, under `src/id_atlas/`:

| Path | Job |
|---|---|
| `engine.py` | OCR with RapidOCR, and recovery of sideways or upside-down photos |
| `mrz.py` | ICAO 9303 machine-readable zone: TD1, TD2 and TD3, with check digits |
| `documents/` | What a document is: the registry (`DocumentSpec`), classification, shared text and date helpers, the field names |
| `countries/` | One module per country; each registers its documents. Costa Rica is the example |
| `barcodes.py`, `imaging.py` | Barcode decoding, image decoding and comparison |
| `pipeline.py` | Merges both sides and applies the review rules |
| `api.py`, `config.py`, `schemas.py`, `cli.py` | HTTP API, settings, response models and the `id-atlas` command |

## Contributing

Contributions are welcome, especially:

- **Real-world accuracy reports.** Run the probe script on your own documents and tell us which fields were
  right or wrong (shapes only, never real values).
- **New document types and countries.** A country is one module in `src/id_atlas/countries/` that registers
  its documents; nothing else needs editing. Pakistani identity documents (the CNIC card and the passport)
  are the next ones wanted: look for issues labelled `help wanted`. The steps are in
  [CONTRIBUTING.md](CONTRIBUTING.md#adding-a-document-type-or-a-country).
- **Lower memory use.**

Please read [CONTRIBUTING.md](CONTRIBUTING.md) first. In short: use the conventional commit style
(`feat(scope): ...`, `fix(scope): ...`, `test(scope): ...`), add tests for new behaviour, and never use real
identity documents in code, tests or issues.

Questions and ideas are welcome in GitHub Discussions. To report a security problem privately, see
[SECURITY.md](SECURITY.md). Everyone taking part is expected to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Acknowledgements

Text recognition is done by [RapidOCR](https://github.com/RapidAI/RapidOCR) running PaddleOCR models on
[ONNX Runtime](https://onnxruntime.ai/). Barcodes are decoded with
[zxing-cpp](https://github.com/zxing-cpp/zxing-cpp).

The OCR models are PP-OCRv6 (detection and recognition) from [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)
by Baidu, converted to ONNX and packaged by RapidOCR. They are licensed under Apache-2.0, like the rest of
RapidOCR. They are not stored in this repository: they are installed with the `rapidocr` package, and the
Docker image carries them together with their licence files. See [NOTICE](NOTICE) for the details.

## License

Copyright 2026 Munir Ahmad. Licensed under the Apache License 2.0. See [LICENSE](LICENSE) and
[NOTICE](NOTICE).
