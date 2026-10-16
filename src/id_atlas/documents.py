"""Document classification and template parsers for Costa Rican identity documents.

The cédula, driver's license and DIMEX parsers were built from a handful of real cards and
specimens, so treat their accuracy as unproven until tested on a larger set of real photos.
"""

import re
import unicodedata
from datetime import date

from .engine import Line
from .schemas import DocumentType, Field, Mrz

# --- Per-document rules -------------------------------------------------------------------------

# Required fields per document type; a missing or unreadable one sends the document to manual review.
_MRZ_REQUIRED = ("document_number", "surname", "given_names", "birth_date", "expiry_date")
REQUIRED: dict[str, tuple[str, ...]] = {
    "cedula": ("id_number", "given_names", "surname1", "birth_date", "expiry_date"),
    "driver_license": ("license_number", "expiry_date", "license_type"),
    "dimex": ("id_number",),
    "passport": _MRZ_REQUIRED,
    "id_mrz": _MRZ_REQUIRED,
}

# Documents that are only complete with both sides; a missing back sends them to review.
BACK_REQUIRED = {"cedula", "driver_license", "dimex"}

# Words (spaces and accents removed) printed on only one side of a document. They tell the sides
# apart, and any of them also identifies the document type.
_MARKERS = {
    "cedula": {
        "front": ("CEDULADEIDENTIDAD", "TRIBUNALSUPREMO"),
        "back": ("DOMICILIOELECTORAL", "NOMBREDELPADRE", "NOMBREDELAMADRE", "LUGARDENACIMIENTO"),
    },
    "driver_license": {
        "front": ("LICENCIADECONDUCIR",),
        "back": ("EDUCACIONVIAL", "CLASIFICACION"),
    },
}


# --- Classification -----------------------------------------------------------------------------


def _squash(text: str) -> str:
    text = unicodedata.normalize("NFD", text.upper())
    return re.sub(r"[^A-Z0-9]", "", "".join(c for c in text if unicodedata.category(c) != "Mn"))


def _blob(lines: list[Line]) -> str:
    # Spaces are dropped because the OCR often merges or splits words.
    return _squash(" ".join(ln.text for ln in lines))


def classify(lines: list[Line], mrz: Mrz | None) -> DocumentType:
    blob = _blob(lines)

    def has(doc: str) -> bool:
        return any(m in blob for words in _MARKERS[doc].values() for m in words)

    if has("driver_license") or "COSEVI" in blob:
        return "driver_license"
    if "DIMEX" in blob or "DOCUMENTODEIDENTIDADMIGRATORIO" in blob:
        return "dimex"
    if has("cedula"):
        return "cedula"
    if mrz:
        return "passport" if mrz.format == "TD3" and mrz.document_code.startswith("P") else "id_mrz"
    if "PASAPORTE" in blob or "PASSPORT" in blob:
        return "passport"
    return "unknown"


def side_guess(lines: list[Line]) -> str | None:
    """'front' or 'back' when the text only fits one side of a known document, else None."""
    blob = _blob(lines)
    sides = {
        side
        for words in _MARKERS.values()
        for side, markers in words.items()
        if any(m in blob for m in markers)
    }
    return sides.pop() if len(sides) == 1 else None


# --- Field extraction helpers -------------------------------------------------------------------

_SEP = r"\s*[:;.]?\s*"
_PUNCT = re.compile(r"^[\s:;.\-]+")
_LABEL_ONLY = re.compile(r"^[A-Za-zÁÉÍÓÚÑáéíóúñ .°ºo]+:\s*$")
_MONTHS = {
    "ENE": 1,
    "FEB": 2,
    "MAR": 3,
    "ABR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AGO": 8,
    "SEP": 9,
    "SET": 9,
    "OCT": 10,
    "NOV": 11,
    "DIC": 12,
}
_DATE = re.compile(
    r"(?<!\d)(\d{1,2})(?!\d)\s*(?:[/\-.]|DE)?\s*(\d{1,2}(?!\d)|[A-ZÁÉ]{3,10})\s*(?:[/\-.]|DE)?\s*(\d{4})(?!\d)",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"(?<!\d)([1-9])[\s-]?(\d{4})[\s-]?(\d{4})(?!\d)")


def _candidates(lines: list[Line], label: str) -> list[tuple[str, Line]]:
    """Text that follows `label`: first on the same line, then the line to its right, then below."""
    for ln in lines:
        if not (m := re.search(label, ln.text, re.IGNORECASE)):
            continue
        found = []
        if re.search(r"\w", rest := _PUNCT.sub("", ln.text[m.end() :])):
            found.append((rest.strip(), ln))
        right = [c for c in lines if c is not ln and c.x > ln.x and abs(c.y - ln.y) <= 0.6 * max(ln.h, c.h)]
        below = [c for c in lines if c.y > ln.y + 0.5 * ln.h and not _LABEL_ONLY.match(c.text)]
        for pool, key in ((right, lambda c: c.x), (below, lambda c: c.y)):
            if pool:
                nearest = min(pool, key=key)
                found.append((nearest.text.strip(), nearest))
                break
        return found
    return []


def _text(lines: list[Line], label: str) -> Field | None:
    """The text that follows a label."""
    if candidates := _candidates(lines, label):
        value, ln = candidates[0]
        return Field(value=value, raw=value, confidence=round(ln.score, 3))
    return None


def _text_match(lines: list[Line], pattern: str) -> Field | None:
    """First line matching `pattern`; the value is its first capture group."""
    for ln in lines:
        if m := re.search(pattern, ln.text, re.IGNORECASE):
            value = m.group(1).strip()
            return Field(value=value or None, raw=value, confidence=round(ln.score, 3))
    return None


def _parse_date(text: str) -> tuple[str | None, str] | None:
    """(ISO date or None if impossible, the matched text), or None when no date-like text is present."""
    if not (m := _DATE.search(text)):
        return None
    day, month, year = m.groups()
    if not month.isdigit():
        month = _MONTHS.get(_squash(month)[:3])
    try:
        return date(int(year), int(month), int(day)).isoformat(), m.group(0).strip()
    except (TypeError, ValueError):
        return None, m.group(0).strip()


def _date_field(lines: list[Line], label: str) -> Field | None:
    for text, ln in _candidates(lines, label):
        if parsed := _parse_date(text):
            return Field(value=parsed[0], raw=parsed[1], confidence=round(ln.score, 3))
    return None


def _present(**candidates: Field | None) -> dict[str, Field]:
    return {k: v for k, v in candidates.items() if v is not None}


# --- Template parsers ---------------------------------------------------------------------------

_BIRTH = r"(?:F\.|FECHA(?:\s+DE)?)\s*NAC\w*"
_EXPIRY = r"VENC(?:E|IMIENTO)"


def parse_cedula(lines: list[Line]) -> dict[str, Field]:
    # Parents' names, birthplace and electoral address are printed on the card but deliberately not read.
    fields = _present(
        given_names=_text(lines, r"NOMBRE(?!\s*(?:DEL?|DE\s+LA)\b)"),
        surname1=_text(lines, r"1\s*[ºo°.]?\s*APELLIDO"),
        surname2=_text(lines, r"2\s*[ºo°.]?\s*APELLIDO"),
        birth_date=_date_field(lines, _BIRTH),
        expiry_date=_date_field(lines, _EXPIRY),
    )
    # The number is printed unlabeled on the front and labeled on the back.
    texts = [(t, ln) for t, ln in _candidates(lines, r"N[UÚ]MERO\s+DE\s+C[EÉ]DULA")] + [
        (ln.text, ln) for ln in lines
    ]
    for text, ln in texts:
        if m := _NUMBER.search(text):
            fields["id_number"] = Field(
                value="".join(m.groups()), raw=m.group(0), confidence=round(ln.score, 3)
            )
            break
    return fields


def parse_license(lines: list[Line]) -> dict[str, Field]:
    return _present(
        license_number=_text_match(lines, r"\b([A-Z]{1,3}-?\d{6,12})\b"),
        issue_date=_date_field(lines, r"EXPEDICI[OÓ]N"),
        birth_date=_date_field(lines, r"NACIMIENTO"),
        expiry_date=_date_field(lines, r"VENCIMIENTO"),
        license_type=_text_match(lines, r"TIPO" + _SEP + r"([A-E]\d?)\b"),
    )


def parse_dimex(lines: list[Line]) -> dict[str, Field]:
    return _present(id_number=_text_match(lines, r"(?<!\d)(\d{11,12})(?!\d)"))


TEMPLATE_PARSERS = {
    "cedula": parse_cedula,
    "driver_license": parse_license,
    "dimex": parse_dimex,
}


# --- Cross-checks and other sources -------------------------------------------------------------

_LICENSE_BARCODE = re.compile(r"^([A-Z]{1,3})(\d{6,12})([A-E]\d?)$")


def reconcile_license_barcode(
    fields: dict[str, Field], barcodes: list[str]
) -> tuple[dict[str, Field], list[str]]:
    """Cross-check a license against its PDF417, which carries the number followed by the license type.

    Seen on one real license only, so a barcode of any other shape is ignored. Agreement raises the
    confidence of both fields; a disagreement never overwrites OCR, it only asks for review.
    """
    fields = dict(fields)
    reasons = []
    for text in barcodes:
        if not (m := _LICENSE_BARCODE.match(re.sub(r"[\s-]", "", text.upper()))):
            continue
        prefix, digits, license_type = m.groups()
        expected = {
            "license_number": (prefix + digits, f"{prefix}-{digits}"),
            "license_type": (license_type, license_type),
        }
        for name, (compact, display) in expected.items():
            field = fields.get(name)
            if field is None or not field.value:
                fields[name] = Field(value=display, raw=text, confidence=0.99)
            elif re.sub(r"[\s-]", "", field.value.upper()) == compact:
                fields[name] = field.model_copy(update={"confidence": max(field.confidence, 0.99)})
            else:
                reasons.append(f"barcode_mismatch:{name}")
        break
    return fields, reasons


def from_mrz(mrz: Mrz) -> dict[str, Field]:
    """Fields of a passport or other MRZ document; confidence reflects whether its check digits passed."""

    def field(value: str | None, ok: bool) -> Field | None:
        return Field(value=value or None, raw=value, confidence=0.99 if ok else 0.5) if value else None

    c = mrz.checks
    return _present(
        document_number=field(mrz.document_number, c["document_number"]),
        surname=field(mrz.surname, mrz.valid),
        given_names=field(mrz.given_names, mrz.valid),
        nationality=field(mrz.nationality, mrz.valid),
        issuing_country=field(mrz.issuing_country, mrz.valid),
        birth_date=field(mrz.birth_date, c["birth_date"]),
        sex=field(mrz.sex, mrz.valid),
        expiry_date=field(mrz.expiry_date, c["expiry_date"]),
    )
