"""Reading text off a card: normalising, finding the value that follows a label, parsing dates.

These helpers are shared by every country module and know no language. What depends on the language of a
card (its label words, month names and the words between the parts of a date) is described by a `Style`,
which a country module passes in through a `Reader`.
"""

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache

from ..engine import Line
from ..schemas import Field

SEP = r"\s*[:;.]?\s*"  # between a label and its value: an optional colon, semicolon or dot

_PUNCT = re.compile(r"^[\s:;.\-]+")
# A line that is only a label ("Name:"): letters, spaces, dots and ordinal signs, then a colon.
_LABEL_ONLY = re.compile(r"^(?:[^\W\d_]|[ .°º])+:\s*$")
_ENGLISH_MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}
_ISO_DATE = re.compile(r"(?<!\d)(\d{4})\s*[/\-.]\s*(\d{1,2})(?!\d)\s*[/\-.]\s*(\d{1,2})(?!\d)")
# OCR mistakes the same few characters for one another (I/l/1, O/0, B/8...); folded together to compare.
_CONFUSABLE = str.maketrans(
    {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "B": "8", "S": "5", "Z": "2", "G": "6"}
)


@dataclass(frozen=True)
class Style:
    """The language-dependent parts of reading a card. Every field is optional: the defaults read
    English month names and day-first dates, and recognise no label words."""

    # Regex of words that mark a line as a field label, such as "NAME|GENDER|DATE\s+OF". A neighbouring
    # line that holds one is never taken as the value of another field.
    label_words: str = ""
    # Month names beyond English, keyed by their first three letters in capitals: {"ENE": 1, "ABR": 4}.
    months: Mapping[str, int] = field(default_factory=dict)
    # Words that may sit between the parts of a date, such as ("DE",) for "12 DE ENERO DE 2020".
    date_joiners: tuple[str, ...] = ()
    # Read 03/04/2030 as 4 March. Leave False for day-first countries, the rule almost everywhere.
    month_first: bool = False


DEFAULT_STYLE = Style()


def squash(text: str) -> str:
    """Upper-case, accents and everything but letters and digits removed."""
    text = unicodedata.normalize("NFD", text.upper())
    return re.sub(r"[^A-Z0-9]", "", "".join(c for c in text if unicodedata.category(c) != "Mn"))


def blob(lines: list[Line]) -> str:
    """All the text of a side, squashed. Spaces are dropped because the OCR often merges or splits words."""
    return squash(" ".join(ln.text for ln in lines))


def fold_confusables(text: str) -> str:
    """`text` without spaces and dashes and with look-alike characters folded together, so two readings
    of the same printed value compare equal even when the OCR mistook an I for a 1."""
    return re.sub(r"[\s-]", "", text.upper()).translate(_CONFUSABLE)


def present(**candidates: Field | None) -> dict[str, Field]:
    """The candidates that were found."""
    return {k: v for k, v in candidates.items() if v is not None}


# --- Dates --------------------------------------------------------------------------------------


@lru_cache
def _day_month_year(joiners: tuple[str, ...]) -> re.Pattern[str]:
    sep = r"(?:[/\-.]" + "".join(f"|{re.escape(j)}" for j in joiners) + r")?"
    return re.compile(
        rf"(?<!\d)(\d{{1,2}})(?!\d)\s*{sep}\s*(\d{{1,2}}(?!\d)|[^\W\d_]{{3,12}})\s*{sep}\s*(\d{{4}})(?!\d)",
        re.IGNORECASE,
    )


def parse_date(text: str, style: Style = DEFAULT_STYLE) -> tuple[str | None, str] | None:
    """(ISO date or None if impossible, the matched text), or None when no date-like text is present.

    Reads year-first dates (1990-01-12) and day-first ones (12/01/1990, 12 JAN 1990); month-first
    (01/12/1990) only when the style says so.
    """
    if m := _ISO_DATE.search(text):
        year, month, day = m.groups()
    elif m := _day_month_year(style.date_joiners).search(text):
        day, month, year = m.groups()
        if style.month_first and month.isdigit():
            day, month = month, day
        if not month.isdigit():
            month = {**_ENGLISH_MONTHS, **style.months}.get(squash(month)[:3])
    else:
        return None
    try:
        return date(int(year), int(month), int(day)).isoformat(), m.group(0).strip()
    except (TypeError, ValueError):
        return None, m.group(0).strip()


# --- Finding values -----------------------------------------------------------------------------


class Reader:
    """The OCR lines of one side, read in the language described by a `Style`."""

    def __init__(self, lines: list[Line], style: Style = DEFAULT_STYLE) -> None:
        self.lines = lines
        self.style = style

    def _is_label(self, text: str) -> bool:
        words = self.style.label_words
        return bool(_LABEL_ONLY.match(text) or (words and re.search(words, text, re.IGNORECASE)))

    def candidates_after(self, label: str) -> list[tuple[str, Line]]:
        """Text that follows `label`: first on the same line, then the nearest line to its right, then the
        nearest below. A neighbouring line that is itself a label is not a value: when this label's value
        was not read, the next field's value must not be handed to it."""
        lines = self.lines
        for ln in lines:
            if not (m := re.search(label, ln.text, re.IGNORECASE)):
                continue
            found = []
            if re.search(r"\w", rest := _PUNCT.sub("", ln.text[m.end() :])):
                found.append((rest.strip(), ln))
            right = [
                c for c in lines if c is not ln and c.x > ln.x and abs(c.y - ln.y) <= 0.6 * max(ln.h, c.h)
            ]
            below = [c for c in lines if c.y > ln.y + 0.5 * ln.h]
            for pool, key in ((right, lambda c: c.x), (below, lambda c: c.y)):
                if pool:
                    nearest = min(pool, key=key)
                    if not self._is_label(nearest.text):
                        found.append((nearest.text.strip(), nearest))
                    break
            return found
        return []

    def text_after(self, label: str) -> Field | None:
        """The text that follows a label."""
        if candidates := self.candidates_after(label):
            value, ln = candidates[0]
            return Field(value=value, raw=value, confidence=round(ln.score, 3))
        return None

    def date_after(self, label: str) -> Field | None:
        """The date that follows a label."""
        for text, ln in self.candidates_after(label):
            if parsed := parse_date(text, self.style):
                return Field(value=parsed[0], raw=parsed[1], confidence=round(ln.score, 3))
        return None

    def text_match(self, pattern: str) -> Field | None:
        """First line matching `pattern`; the value is its first capture group."""
        for ln in self.lines:
            if m := re.search(pattern, ln.text, re.IGNORECASE):
                value = m.group(1).strip()
                return Field(value=value or None, raw=value, confidence=round(ln.score, 3))
        return None
