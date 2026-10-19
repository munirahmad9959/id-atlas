"""Read one identity document from its front (and back) image into a single combined result."""

import time
from dataclasses import dataclass

import numpy as np

from . import barcodes, documents, engine, imaging
from . import mrz as mrz_module
from .config import Settings
from .documents.registry import DocumentSpec, UnknownDocumentType
from .schemas import DocumentType, ExtractionResult, Field, Mrz, Side, SideResult


@dataclass
class _Side:
    name: Side
    image: np.ndarray
    lines: list[engine.Line]
    mrz: Mrz | None
    barcodes: list[str]
    doc_type: DocumentType
    guess: str | None  # which side of the document the text suggests: "front", "back" or None


def _read_side(name: Side, data: bytes, settings: Settings) -> _Side:
    try:
        img = imaging.open_image(data)
    except imaging.InvalidImage as exc:
        raise imaging.InvalidImage(f"{name}: {exc}") from exc
    image = imaging.to_bgr(img, settings.max_image_side)
    lines = engine.read_lines(image, settings.rotation_retry_below)
    mrz = mrz_module.read([ln.text for ln in lines])
    # Barcodes come from a larger copy: shrinking to OCR size can destroy small bars.
    codes = barcodes.decode(imaging.to_bgr(img, settings.barcode_max_side))
    return _Side(name, image, lines, mrz, codes, documents.classify(lines, mrz), documents.side_guess(lines))


def _side_fields(side: _Side, spec: DocumentSpec | None) -> dict[str, Field]:
    if spec is None:
        parsed = {}
    elif spec.mrz_based:
        parsed = documents.from_mrz(side.mrz) if side.mrz else {}
    else:
        parsed = spec.parse(side.lines) if spec.parse else {}
    return {k: v.model_copy(update={"side": side.name}) for k, v in parsed.items()}


def extract_document(
    front: bytes,
    back: bytes | None,
    settings: Settings,
    hint: DocumentType | None = None,
    *,
    check_sides: bool = True,
) -> ExtractionResult:
    """Read one document from its front (and back) image and return a single combined result.

    `hint` forces the document type instead of detecting it. With `check_sides` off, a lone image is
    not flagged for a missing back.
    """
    started = time.perf_counter()
    if hint is not None and documents.get(hint) is None:
        raise UnknownDocumentType(f"unknown document_type: {hint}")
    sides = [_read_side("front", front, settings)]
    if back is not None:
        sides.append(_read_side("back", back, settings))

    recognised = [s.doc_type for s in sides if s.doc_type != "unknown"]
    doc_type: DocumentType = hint or (recognised[0] if recognised else "unknown")
    mrz = next((s.mrz for s in sides if s.mrz), None)

    spec = documents.get(doc_type)
    per_side = [_side_fields(s, spec) for s in sides]
    fields: dict[str, Field] = {}
    for parsed in per_side:  # the front wins on a tie, but a valid value beats an unreadable one
        for name, field in parsed.items():
            current = fields.get(name)
            if current is None or (current.value is None and field.value is not None):
                fields[name] = field

    codes = [code for s in sides for code in s.barcodes]
    barcode_reasons: list[str] = []
    if spec and spec.reconcile:
        fields, barcode_reasons = spec.reconcile(fields, codes)

    reasons = _review_reasons(doc_type, fields, mrz, settings) + barcode_reasons
    if check_sides:
        reasons += _side_reasons(doc_type, sides, per_side)

    return ExtractionResult(
        document_type=doc_type,
        fields=fields,
        mrz=mrz,
        barcodes=codes,
        sides=[
            SideResult(side=s.name, document_type=s.doc_type, fields_found=len(f))
            for s, f in zip(sides, per_side)
        ],
        needs_review=bool(reasons),
        review_reasons=reasons,
        elapsed_ms=round((time.perf_counter() - started) * 1000),
    )


def extract(data: bytes, settings: Settings, hint: DocumentType | None = None) -> ExtractionResult:
    """Single-image extraction: no side checks, since one image cannot show a missing back."""
    return extract_document(data, None, settings, hint, check_sides=False)


def _side_reasons(doc_type: str, sides: list[_Side], per_side: list[dict[str, Field]]) -> list[str]:
    if len(sides) == 1:
        spec = documents.get(doc_type)
        return ["missing_back_side"] if spec and spec.two_sided else []

    front, back = sides
    reasons = []
    if imaging.same_picture(front.image, back.image):
        reasons.append("duplicate_sides")
    elif "unknown" not in (front.doc_type, back.doc_type) and front.doc_type != back.doc_type:
        reasons.append("sides_mismatch")
    elif front.guess == "back" or back.guess == "front":
        reasons.append("sides_possibly_swapped")

    # A field printed on both sides (such as the cédula number) must agree.
    for name in per_side[0].keys() & per_side[1].keys():
        a, b = per_side[0][name].value, per_side[1][name].value
        if a and b and a != b:
            reasons.append(f"field_conflict:{name}")
    return reasons


def _review_reasons(
    doc_type: str, fields: dict[str, Field], mrz: Mrz | None, settings: Settings
) -> list[str]:
    spec = documents.get(doc_type)
    reasons = []
    if doc_type == "unknown":
        reasons.append("unknown_document_type")
    if spec and not spec.verified:
        reasons.append("template_unverified")
    if mrz and not mrz.valid:
        reasons.append("mrz_checksum_failed")
    for name in spec.required if spec else ():
        field = fields.get(name)
        if field is None:
            reasons.append(f"missing:{name}")
        elif field.value is None:
            reasons.append(f"invalid:{name}")
        elif field.confidence < settings.review_below:
            reasons.append(f"low_confidence:{name}")
    return reasons
