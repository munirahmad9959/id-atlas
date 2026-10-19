# Changelog

All notable changes are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to follow
[Semantic Versioning](https://semver.org/).

## [0.1.0] - unreleased

First version.

### Added

- HTTP API: `POST /v1/extract/document`, `POST /v1/extract`, `GET /v1/documents` and `GET /health`, with an
  optional API key.
- OCR on CPU with RapidOCR (PP-OCRv6 small), including recovery of sideways and upside-down photos.
- ICAO 9303 machine-readable zone parser for TD1, TD2 and TD3 that verifies every check digit.
- A document registry: a country is one module in `id_atlas.countries` that registers its documents, and it
  is found automatically.
- Costa Rican cédula de identidad, driver's license (cross-checked against its PDF417 barcode) and DIMEX.
- Front and back merging with cross-checks and `review_reasons`.
- Canonical field names shared by every country (`documents/fields.py`) and a `country` in every result.
- Language-neutral text helpers (`Style`, `Reader`): English month names and year-first dates by default,
  with label words, extra months and date joiners supplied per country.
- Dockerfile and probe scripts for local diagnosis.
- GitHub Actions CI with three checks: `lint`, `test` and `docker`.
- Contributing guide, code of conduct, security policy, notice file, and issue and pull request templates.

### Notes

- Before this release the code was Costa-Rica-only. The field names were `id_number`, `license_number`,
  `surname1`, `surname2` and `license_type`; they are now `document_number`, `document_number`, `surname`,
  `second_surname` and `license_category`, and review reasons use the same names.
