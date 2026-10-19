"""Reading text off a card: normalising, finding the value that follows a label, parsing dates.

These helpers are shared by every country module. They know nothing about one country except what a
module passes in.
"""

import re
import unicodedata
from datetime import date

from ..engine import Line
from ..schemas import Field

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

# Lines carrying one of these words are another field's label (or a label and its value).
_LABEL_WORDS = re.compile(
    r"NOMBRE|APELLIDO|NACIMIENTO|F\.\s*NAC|VENC|EXPEDICI|DOMICILIO|PADRE|MADRE|N[UÚ]MERO\s+DE\s+C[EÉ]DULA",
    re.IGNORECASE,
)

SEP = _SEP  # between a label and its value: an optional colon, semicolon or dot


def squash(text: str) -> str:
    """Upper-case, accents and everything but letters and digits removed."""
    text = unicodedata.normalize("NFD", text.upper())
    return re.sub(r"[^A-Z0-9]", "", "".join(c for c in text if unicodedata.category(c) != "Mn"))


def blob(lines: list[Line]) -> str:
    """All the text of a side, squashed. Spaces are dropped because the OCR often merges or splits words."""
    return squash(" ".join(ln.text for ln in lines))


def _is_label(text: str) -> bool:
    return bool(_LABEL_ONLY.match(text) or _LABEL_WORDS.search(text))


def candidates_after(lines: list[Line], label: str) -> list[tuple[str, Line]]:
    """Text that follows `label`: first on the same line, then the nearest line to its right, then the
    nearest below. A neighbouring line that is itself a label is not a value: when this label's value
    was not read, the next field's value must not be handed to it."""
    for ln in lines:
        if not (m := re.search(label, ln.text, re.IGNORECASE)):
            continue
        found = []
        if re.search(r"\w", rest := _PUNCT.sub("", ln.text[m.end() :])):
            found.append((rest.strip(), ln))
        right = [c for c in lines if c is not ln and c.x > ln.x and abs(c.y - ln.y) <= 0.6 * max(ln.h, c.h)]
        below = [c for c in lines if c.y > ln.y + 0.5 * ln.h]
        for pool, key in ((right, lambda c: c.x), (below, lambda c: c.y)):
            if pool:
                nearest = min(pool, key=key)
                if not _is_label(nearest.text):
                    found.append((nearest.text.strip(), nearest))
                break
        return found
    return []


def text_after(lines: list[Line], label: str) -> Field | None:
    """The text that follows a label."""
    if candidates := candidates_after(lines, label):
        value, ln = candidates[0]
        return Field(value=value, raw=value, confidence=round(ln.score, 3))
    return None


def text_match(lines: list[Line], pattern: str) -> Field | None:
    """First line matching `pattern`; the value is its first capture group."""
    for ln in lines:
        if m := re.search(pattern, ln.text, re.IGNORECASE):
            value = m.group(1).strip()
            return Field(value=value or None, raw=value, confidence=round(ln.score, 3))
    return None


def parse_date(text: str) -> tuple[str | None, str] | None:
    """(ISO date or None if impossible, the matched text), or None when no date-like text is present."""
    if not (m := _DATE.search(text)):
        return None
    day, month, year = m.groups()
    if not month.isdigit():
        month = _MONTHS.get(squash(month)[:3])
    try:
        return date(int(year), int(month), int(day)).isoformat(), m.group(0).strip()
    except (TypeError, ValueError):
        return None, m.group(0).strip()


def date_after(lines: list[Line], label: str) -> Field | None:
    """The date that follows a label."""
    for text, ln in candidates_after(lines, label):
        if parsed := parse_date(text):
            return Field(value=parsed[0], raw=parsed[1], confidence=round(ln.score, 3))
    return None


def present(**candidates: Field | None) -> dict[str, Field]:
    """The candidates that were found."""
    return {k: v for k, v in candidates.items() if v is not None}
