"""Barcode decoding for card photos."""

import cv2
import numpy as np
import zxingcpp

# Enlarging a photo bigger than this costs a lot, and its bars are already wide enough.
_ENLARGE_UP_TO = 2000


def decode(image: np.ndarray) -> list[str]:
    """Texts of the barcodes found in a BGR image, retrying enlarged because the bars in a card photo
    are often only 1-2 px wide. Returns as soon as one attempt decodes something."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    attempts = [(gray, zxingcpp.Binarizer.LocalAverage), (gray, zxingcpp.Binarizer.GlobalHistogram)]
    if max(gray.shape) <= _ENLARGE_UP_TO:
        big = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        enhanced = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(big)
        attempts += [(big, zxingcpp.Binarizer.LocalAverage), (enhanced, zxingcpp.Binarizer.LocalAverage)]
    for img, binarizer in attempts:
        if found := [r.text for r in zxingcpp.read_barcodes(img, binarizer=binarizer) if r.text]:
            return found
    return []
