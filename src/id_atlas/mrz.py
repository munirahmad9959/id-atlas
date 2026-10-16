"""ICAO 9303 machine-readable zone: locate in OCR output, repair, parse, verify check digits."""

import re
from datetime import date

from .schemas import Mrz

_WEIGHTS = (7, 3, 1)
_TO_DIGIT = str.maketrans({"O": "0", "Q": "0", "D": "0", "I": "1", "B": "8", "S": "5", "Z": "2", "G": "6"})
_TO_ALPHA = str.maketrans({"0": "O", "1": "I", "8": "B", "5": "S", "2": "Z", "6": "G"})
_FILLERS = str.maketrans({"«": "<", "‹": "<", "〈": "<"})
_FORMATS = {"TD3": (2, 44), "TD1": (3, 30)}
_LENGTH_SLACK = 4


def check_digit(data: str) -> int:
    total = 0
    for i, ch in enumerate(data):
        value = int(ch) if ch.isdigit() else ord(ch) - 55 if ch.isalpha() else 0
        total += value * _WEIGHTS[i % 3]
    return total % 10


def _clean(text: str) -> str:
    text = text.upper().translate(_FILLERS)
    return re.sub(r"[^A-Z0-9<]", "", text)


def _fit(line: str, length: int) -> str:
    return line[:length].ljust(length, "<")


def locate(texts: list[str]) -> tuple[str, list[str]] | None:
    """Find the MRZ block in OCR lines given in reading order. Returns (format, lines)."""
    cleaned = [_clean(t) for t in texts]
    for fmt, (count, length) in _FORMATS.items():
        for start in range(len(cleaned) - count + 1):
            window = cleaned[start : start + count]
            if not all(abs(len(w) - length) <= _LENGTH_SLACK for w in window):
                continue
            if not window[0][:1].isalpha() or not any("<" in w or w.isdigit() for w in window):
                continue
            return fmt, [_fit(w, length) for w in window]
    return None


def _verified(field: str, check: str) -> tuple[str, bool]:
    """Check a field against its check digit, retrying the common O/0 confusion."""
    expected = check.translate(_TO_DIGIT)
    if expected == "<":
        expected = "0"
    for candidate in dict.fromkeys((field, field.replace("O", "0"))):
        if expected.isdigit() and check_digit(candidate) == int(expected):
            return candidate, True
    return field, False


def _date(yymmdd: str, *, birth: bool) -> str | None:
    digits = yymmdd.translate(_TO_DIGIT)
    if len(digits) != 6 or not digits.isdigit():
        return None
    yy = int(digits[:2])
    year = (1900 + yy if yy > date.today().year % 100 else 2000 + yy) if birth else 2000 + yy
    try:
        return date(year, int(digits[2:4]), int(digits[4:6])).isoformat()
    except ValueError:
        return None


def _names(block: str) -> tuple[str, str]:
    block = block.translate(_TO_ALPHA)
    surname, _, given = block.partition("<<")
    return surname.replace("<", " ").strip(), given.replace("<", " ").strip()


def _sex(ch: str) -> str | None:
    return {"M": "M", "F": "F", "<": "X", "X": "X"}.get(ch)


def _build(fmt: str, lines: list[str], **v) -> Mrz:
    checks = v.pop("checks")
    applicable = [ok for key, ok in checks.items() if key != "personal_number" or v["personal_number"]]
    return Mrz(format=fmt, lines=lines, checks=checks, valid=all(applicable), **v)


def parse_td3(lines: list[str]) -> Mrz:
    l1, l2 = lines
    number, number_ok = _verified(l2[0:9], l2[9])
    _, birth_ok = _verified(l2[13:19], l2[19])
    _, expiry_ok = _verified(l2[21:27], l2[27])
    personal, personal_ok = _verified(l2[28:42], l2[42])
    composite = l2[0:10] + l2[13:20] + l2[21:43]
    _, composite_ok = _verified(composite, l2[43])
    surname, given = _names(l1[5:44])
    return _build(
        "TD3",
        lines,
        document_code=l1[0:2].replace("<", "").translate(_TO_ALPHA),
        issuing_country=l1[2:5].translate(_TO_ALPHA).replace("<", ""),
        surname=surname,
        given_names=given,
        document_number=number.rstrip("<"),
        nationality=l2[10:13].translate(_TO_ALPHA).replace("<", ""),
        birth_date=_date(l2[13:19], birth=True),
        sex=_sex(l2[20]),
        expiry_date=_date(l2[21:27], birth=False),
        personal_number=personal.strip("<"),
        checks={
            "document_number": number_ok,
            "birth_date": birth_ok,
            "expiry_date": expiry_ok,
            "personal_number": personal_ok,
            "composite": composite_ok,
        },
    )


def parse_td1(lines: list[str]) -> Mrz:
    l1, l2, l3 = lines
    number, number_ok = _verified(l1[5:14], l1[14])
    _, birth_ok = _verified(l2[0:6], l2[6])
    _, expiry_ok = _verified(l2[8:14], l2[14])
    composite = l1[5:30] + l2[0:7] + l2[8:15] + l2[18:29]
    _, composite_ok = _verified(composite, l2[29])
    surname, given = _names(l3)
    return _build(
        "TD1",
        lines,
        document_code=l1[0:2].replace("<", "").translate(_TO_ALPHA),
        issuing_country=l1[2:5].translate(_TO_ALPHA).replace("<", ""),
        surname=surname,
        given_names=given,
        document_number=number.rstrip("<"),
        nationality=l2[15:18].translate(_TO_ALPHA).replace("<", ""),
        birth_date=_date(l2[0:6], birth=True),
        sex=_sex(l2[7]),
        expiry_date=_date(l2[8:14], birth=False),
        personal_number=l1[15:30].strip("<"),
        checks={
            "document_number": number_ok,
            "birth_date": birth_ok,
            "expiry_date": expiry_ok,
            "composite": composite_ok,
        },
    )


def read(texts: list[str]) -> Mrz | None:
    found = locate(texts)
    if not found:
        return None
    fmt, lines = found
    return parse_td3(lines) if fmt == "TD3" else parse_td1(lines)
