"""OCR engine: RapidOCR (PP-OCRv6 small models on ONNX Runtime, bundled with the package)."""

import threading
from dataclasses import dataclass
from functools import lru_cache

import cv2
import numpy as np
from rapidocr import RapidOCR


@dataclass(frozen=True)
class Line:
    """One recognised line of text. `x` is the box's left edge, `y` its vertical centre, `w` and `h` its size."""

    text: str
    score: float
    x: float
    y: float
    w: float
    h: float


@lru_cache
def _engine() -> RapidOCR:
    # The built-in 180-degree line classifier is off on purpose. It "fixes" upside-down text, so an
    # upside-down page would read fine but come back bottom-to-top, which breaks every parser that
    # relies on reading order. Without it, such a page reads as noise and read_lines() re-orients it.
    return RapidOCR(params={"Global.log_level": "warning", "Global.use_cls": False})


# One inference at a time: bounds CPU use and keeps the shared engine safe.
_lock = threading.Lock()


def _run(image: np.ndarray) -> list[Line]:
    with _lock:
        result = _engine()(image)
    if result.txts is None:
        return []
    lines = [
        Line(
            text,
            float(score),
            float(box[:, 0].min()),
            float(box[:, 1].mean()),
            float(np.ptp(box[:, 0])),
            float(np.ptp(box[:, 1])),
        )
        for box, text, score in zip(result.boxes, result.txts, result.scores)
    ]
    return sorted(lines, key=lambda ln: ln.y)


def _upright(lines: list[Line]) -> list[Line]:
    """Lines that read left to right. The model also reads sideways text, as tall boxes, so confidence
    alone cannot tell a rotated page from an upright one; the box shape can."""
    return [ln for ln in lines if ln.w >= ln.h]


def _quality(lines: list[Line]) -> float:
    return sum(ln.score * len(ln.text) for ln in _upright(lines))


_ROTATIONS = (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180, cv2.ROTATE_90_COUNTERCLOCKWISE)


def read_lines(image: np.ndarray, retry_below: float) -> list[Line]:
    """OCR a BGR image, top to bottom. A clean reading with 2+ upright lines is returned as is; anything
    weaker is retried at the other rotations and the best reading wins (a sideways phone photo)."""
    best = _run(image)
    good = _upright(best)
    if len(good) >= 2 and sum(ln.score for ln in good) / len(good) >= retry_below:
        return best
    for code in _ROTATIONS:
        candidate = _run(cv2.rotate(image, code))
        if _quality(candidate) > _quality(best):
            best = candidate
    return best


def warm_up() -> None:
    """Load the models now, so the first real request does not pay for it."""
    _run(np.full((64, 256, 3), 255, dtype=np.uint8))
