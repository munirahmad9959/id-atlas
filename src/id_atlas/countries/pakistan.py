"""Pakistani identity documents: the National Identity Card (CNIC), smart card, front side.

Verified on real cards. The back prints only Urdu text, a QR code and the number again, none of which the
bundled OCR model reads, so only the front is read.
"""

import re

from ..documents import DocumentSpec, register
from ..documents.text import Style, parse_date, present
from ..engine import Line
from ..schemas import Field

COUNTRY = "PAK"

# The English labels printed on the card. A line holding one is never taken as the value of another label.
STYLE = Style(label_words=r"\bNAME\b|GENDER|COUNTRY\s*OF\s*STAY|\bSTAY\b|IDENTITY\s*NUMBER|DATE\s*OF|HOLDER")

_NUMBER = re.compile(r"(?<!\d)(\d{5})[\s-]?(\d{7})[\s-]?(\d)(?!\d)")
_SEX = re.compile(r"^[MFX]$")


def _label(words: str, *, at_start: bool = False) -> re.Pattern[str]:
    """A label, with the OCR free to merge or split its words. "Name" must start the line, or it would also
    match the end of "Father Name"."""
    return re.compile(("^\\s*" if at_start else "") + r"\s*".join(words.split()), re.IGNORECASE)


def _value(lines: list[Line], label: re.Pattern[str]) -> tuple[str, Line] | None:
    """The text that belongs to a label: whatever follows it on its line, else the nearest line below it
    that sits under the label's own part of the line (the OCR sometimes merges two side-by-side labels into
    one line). The card is a grid, so a neighbour to the right is another cell, never the value. A label
    with no value of its own gives None, not the next cell's value."""
    for ln in lines:
        if not (m := label.search(ln.text)):
            continue
        rest = re.sub(r"^[\s:;.\-]+", "", ln.text[m.end() :])
        if re.search(r"\w", rest) and not re.search(STYLE.label_words, rest, re.IGNORECASE):
            return rest.strip(), ln
        left = ln.x + ln.w * m.start() / len(ln.text)
        right = ln.x + ln.w * m.end() / len(ln.text)
        below = [c for c in lines if c.y > ln.y + 0.5 * ln.h and c.x < right and c.x + c.w > left]
        nearest = min(below, key=lambda c: c.y) if below else None
        if nearest and not re.search(STYLE.label_words, nearest.text, re.IGNORECASE):
            return nearest.text.strip(), nearest
        return None
    return None


def _text(lines: list[Line], label: re.Pattern[str]) -> Field | None:
    # The Urdu line printed under each English one comes out as noise; text without a Latin letter is not read.
    if (found := _value(lines, label)) and re.search(r"[A-Za-z]", found[0]):
        return Field(value=found[0], raw=found[0], confidence=round(found[1].score, 3))
    return None


def _date(lines: list[Line], label: re.Pattern[str]) -> Field | None:
    if (found := _value(lines, label)) and (parsed := parse_date(found[0], STYLE)):
        return Field(value=parsed[0], raw=parsed[1], confidence=round(found[1].score, 3))
    return None


def _sex(lines: list[Line]) -> Field | None:
    if (found := _value(lines, _label("Gender"))) and _SEX.match(text := found[0].upper()):
        return Field(value=text, raw=found[0], confidence=round(found[1].score, 3))
    return None


def parse_cnic(lines: list[Line]) -> dict[str, Field]:
    fields = present(
        full_name=_text(lines, _label("Name", at_start=True)),
        father_name=_text(lines, _label("Father Name")),
        husband_name=_text(lines, _label("Husband Name")),
        sex=_sex(lines),
        country_of_stay=_text(lines, _label("C[a-z]{1,2}ntry of Stay")),
        birth_date=_date(lines, _label("Date of Birth")),
        issue_date=_date(lines, _label("Date of Issue")),
        expiry_date=_date(lines, _label("Date of Expiry")),
    )
    # The OCR sometimes misses the "Identity Number" label, so the number is found by its shape instead.
    for ln in lines:
        if m := _NUMBER.search(ln.text):
            fields["document_number"] = Field(
                value="".join(m.groups()), raw=m.group(0), confidence=round(ln.score, 3)
            )
            break
    return fields


register(
    DocumentSpec(
        type="cnic",
        country=COUNTRY,
        name="Pakistani National Identity Card (CNIC)",
        parse=parse_cnic,
        required=("document_number", "full_name", "birth_date", "expiry_date"),
        # "Islamic Republic of Pakistan" is not a marker: the passport prints it too.
        front_markers=("National Identity Card",),
        verified=True,
    )
)
