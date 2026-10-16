"""Image decoding and comparison."""

import io

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

# Mean gray difference (0-255, on 32x32 thumbnails) under which two images count as the same picture.
_DUPLICATE_DIFF = 4.0


class InvalidImage(ValueError):
    """The bytes are not an image the service can read."""


def open_image(data: bytes) -> Image.Image:
    """Decode an upload to RGB, applying its EXIF orientation."""
    try:
        return ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidImage("not a readable image") from exc


def to_bgr(img: Image.Image, max_side: int) -> np.ndarray:
    """A BGR array no larger than `max_side` on its longest side (the original is left untouched)."""
    if max(img.size) > max_side:
        img = img.copy()
        img.thumbnail((max_side, max_side), Image.LANCZOS)
    return np.ascontiguousarray(np.asarray(img)[:, :, ::-1])  # RGB -> BGR


def load_image(data: bytes, max_side: int) -> np.ndarray:
    return to_bgr(open_image(data), max_side)


def same_picture(a: np.ndarray, b: np.ndarray) -> bool:
    """True when two images are visually the same, such as one photo uploaded as both sides."""

    def thumb(img: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.int16)

    return float(np.abs(thumb(a) - thumb(b)).mean()) < _DUPLICATE_DIFF
