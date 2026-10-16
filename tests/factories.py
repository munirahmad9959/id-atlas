"""Shared test data: hand-built OCR lines and MRZ fixtures. All people and numbers are fictional."""

import io

import numpy as np
import zxingcpp
from PIL import Image, ImageDraw, ImageFont

from id_atlas import mrz
from id_atlas.engine import Line

# The ICAO 9303 specimen documents (Anna Maria Eriksson of Utopia), valid by construction.
TD3 = [
    "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
    "L898902C36UTO7408122F1204159ZE184226B<<<<<10",
]
TD1 = [
    "I<UTOD231458907<<<<<<<<<<<<<<<",
    "7408122F1204159UTO<<<<<<<<<<<6",
    "ERIKSSON<<ANNA<MARIA<<<<<<<<<<",
]


def make_td3(*, number="X1234567", nationality="CRI", dob="900101", sex="F", expiry="300101", personal=""):
    """A TD3 passport MRZ with correct check digits, for cases the ICAO specimen does not cover."""
    cd = mrz.check_digit
    line1 = "P<CRIPRUEBA<<ANA<MARIA".ljust(44, "<")
    num, pers = number.ljust(9, "<"), personal.ljust(14, "<")
    body = f"{num}{cd(num)}{nationality}{dob}{cd(dob)}{sex}{expiry}{cd(expiry)}{pers}{cd(pers) if personal else '<'}"
    composite = body[0:10] + body[13:20] + body[21:43]
    return [line1, body + str(cd(composite))]


def line(text: str, x: float = 30, y: float = 30, score: float = 0.99, h: float = 24) -> Line:
    """One OCR line; its width follows the text length, like a real box."""
    return Line(text, score, x, y, 12 * len(text), h)


def stacked(*texts: str, score: float = 0.99) -> list[Line]:
    """Lines one under another, as a card's rows come back from the OCR."""
    return [line(t, y=30 + i * 40, score=score) for i, t in enumerate(texts)]


def card_image(*rows: str, size: tuple[int, int] = (900, 360), background="white") -> Image.Image:
    """A page with one row of black text per argument, like the printed rows of a card."""
    img = Image.new("RGB", size, background)
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=34)
    for i, text in enumerate(rows):
        draw.text((30, 30 + i * 90), text, fill="black", font=font)
    return img


def barcode_image(
    fmt: zxingcpp.BarcodeFormat, text: str = "TEST-PAYLOAD-123456", scale: int = 3
) -> Image.Image:
    return Image.fromarray(
        np.array(zxingcpp.write_barcode_to_image(zxingcpp.create_barcode(text, fmt), scale=scale))
    ).convert("RGB")


def encode(img: Image.Image, fmt: str = "PNG", **options) -> bytes:
    buffer = io.BytesIO()
    img.convert("RGB").save(buffer, fmt, **options)
    return buffer.getvalue()


def bgr(img: Image.Image) -> np.ndarray:
    """The array the OCR engine takes: BGR, as OpenCV orders it."""
    return np.ascontiguousarray(np.asarray(img.convert("RGB"))[:, :, ::-1])
