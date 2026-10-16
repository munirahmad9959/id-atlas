"""Try many barcode-reading strategies on one image and report which (if any) decodes it.

Usage: uv run python scripts/probe_barcode.py path/to/image.jpg

Prints formats and payload LENGTHS only, never the payload, so the output is safe to share.
"""

import sys

import cv2
import numpy as np
import zxingcpp
from PIL import Image, ImageOps

if len(sys.argv) != 2:
    sys.exit(__doc__)
img = np.asarray(ImageOps.exif_transpose(Image.open(sys.argv[1])).convert("L"))
print(f"image: {img.shape[1]}x{img.shape[0]} px")

variants = {"original": img}
variants["clahe"] = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(img)
variants["sharpened"] = cv2.addWeighted(img, 1.8, cv2.GaussianBlur(img, (0, 0), 3), -0.8, 0)
variants["otsu"] = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
for scale in (0.5, 2.0):
    variants[f"scaled x{scale}"] = cv2.resize(
        img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    )
# Bars are often only in the lower or upper part of a card photo, so scan each half at higher zoom too.
h = img.shape[0]
variants["top half x2"] = cv2.resize(img[: h // 2], None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
variants["bottom half x2"] = cv2.resize(img[h // 2 :], None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

# The decoder can miss a barcode on a busy card, so also zoom into overlapping tiles of the photo.
rows = cols = 3
tile_h, tile_w = int(h / rows * 1.5), int(img.shape[1] / cols * 1.5)
for r in range(rows):
    for c in range(cols):
        y0 = min(int(r * h / rows), h - tile_h)
        x0 = min(int(c * img.shape[1] / cols), img.shape[1] - tile_w)
        tile = img[y0 : y0 + tile_h, x0 : x0 + tile_w]
        variants[f"tile r{r}c{c} x3"] = cv2.resize(tile, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)

hits = 0
for name, variant in variants.items():
    for binarizer in zxingcpp.Binarizer.__members__.values():
        if binarizer == zxingcpp.Binarizer.BoolCast:
            continue
        results = zxingcpp.read_barcodes(variant, binarizer=binarizer)
        for r in results:
            hits += 1
            print(
                f"DECODED  variant={name:<15} binarizer={binarizer.name:<15} format={r.format.name:<10} payload_chars={len(r.text)}"
            )
if not hits:
    print(
        "NOT DECODED by any strategy. The barcode may be unsupported, too small/blurred, or partly hidden by glare."
    )
