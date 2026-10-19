"""Telling which document a page is, and which side of it."""

from ..engine import Line
from ..schemas import Mrz
from . import registry
from .generic import PASSPORT_WORDS
from .text import blob


def classify(lines: list[Line], mrz: Mrz | None) -> str:
    """The type of document a side belongs to, or "unknown".

    The registered document with the most of its markers on the page wins; on a tie, the one registered
    first. Without any marker, a machine-readable zone makes it a passport or another MRZ document.
    """
    text = blob(lines)
    best, best_hits = None, 0
    for spec in registry.specs():
        if (hits := sum(m in text for m in spec.markers)) > best_hits:
            best, best_hits = spec, hits
    if best:
        return best.type
    if mrz:
        return "passport" if mrz.format == "TD3" and mrz.document_code.startswith("P") else "id_mrz"
    if any(word in text for word in PASSPORT_WORDS):
        return "passport"
    return "unknown"


def side_guess(lines: list[Line]) -> str | None:
    """'front' or 'back' when the text only fits one side of a known document, else None."""
    text = blob(lines)
    sides = set()
    for spec in registry.specs():
        for side, markers in (("front", spec.front_markers), ("back", spec.back_markers)):
            if any(m in text for m in markers):
                sides.add(side)
    return sides.pop() if len(sides) == 1 else None
