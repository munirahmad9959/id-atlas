import cv2
import numpy as np
import pytest
import zxingcpp
from factories import barcode_image, bgr, card_image
from PIL import Image
from zxingcpp import BarcodeFormat

from id_atlas import barcodes

TEXT = "TEST-PAYLOAD-123456"


def page_with(*codes: tuple[Image.Image, tuple[int, int]], size=(900, 500)) -> np.ndarray:
    page = Image.new("RGB", size, "white")
    for img, position in codes:
        page.paste(img, position)
    return bgr(page)


@pytest.mark.parametrize(
    "fmt, scale",
    [
        (BarcodeFormat.PDF417, 3),
        (BarcodeFormat.Code128, 2),
        (BarcodeFormat.QRCode, 5),
        (BarcodeFormat.DataMatrix, 6),
    ],
    ids=["pdf417", "code128", "qr", "datamatrix"],
)
def test_common_barcode_formats_are_decoded(fmt, scale):
    assert barcodes.decode(page_with((barcode_image(fmt, TEXT, scale), (40, 40)))) == [TEXT]


def test_several_barcodes_on_one_page():
    qr = barcode_image(BarcodeFormat.QRCode, "QR-ONE", 5)
    bars = barcode_image(BarcodeFormat.Code128, "BARS-TWO", 2)
    assert sorted(barcodes.decode(page_with((qr, (40, 40)), (bars, (300, 300))))) == ["BARS-TWO", "QR-ONE"]


@pytest.mark.parametrize(
    "image", [np.full((300, 600, 3), 255, np.uint8), bgr(card_image("Just text", "no bars"))]
)
def test_no_barcode_means_an_empty_list(image):
    assert barcodes.decode(image) == []


@pytest.mark.parametrize("scale, factor, blur", [(2, 0.7, 0.9), (3, 0.6, 1.1)])
def test_bars_only_a_pixel_wide_need_the_enlarged_retry(scale, factor, blur):
    # A barcode in a full-card phone photo: bars about one pixel wide, slightly soft.
    code = np.array(
        zxingcpp.write_barcode_to_image(
            zxingcpp.create_barcode("LIC-0123456789", BarcodeFormat.PDF417), scale=scale
        )
    )
    code = cv2.resize(code, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
    canvas = np.full((1600, 900), 255, np.uint8)
    canvas[1200 : 1200 + code.shape[0], 100 : 100 + code.shape[1]] = code
    canvas = cv2.GaussianBlur(canvas, (0, 0), blur)

    assert not zxingcpp.read_barcodes(canvas), "too easy: a plain read already works, so this proves nothing"
    assert barcodes.decode(cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)) == ["LIC-0123456789"]


def test_a_large_rotated_soft_low_contrast_photo():
    big = barcode_image(BarcodeFormat.PDF417, TEXT, 3).resize((1100, 220))
    photo = np.asarray(page_with((big, (200, 300)), size=(1500, 900)))
    height, width = photo.shape[:2]
    tilted = cv2.warpAffine(
        photo,
        cv2.getRotationMatrix2D((width / 2, height / 2), 4, 1),
        (width, height),
        borderValue=(255, 255, 255),
    )
    soft = cv2.convertScaleAbs(cv2.GaussianBlur(tilted, (0, 0), 2.2), alpha=0.6, beta=70)
    assert barcodes.decode(soft) == [TEXT]


# --- how hard it tries (counting decoder calls) -------------------------------------------------


@pytest.fixture
def calls(monkeypatch):
    count = []
    real = zxingcpp.read_barcodes
    monkeypatch.setattr(zxingcpp, "read_barcodes", lambda *a, **k: (count.append(1), real(*a, **k))[1])
    return count


def test_it_stops_at_the_first_attempt_that_decodes(calls):
    barcodes.decode(page_with((barcode_image(BarcodeFormat.QRCode, TEXT, 5), (40, 40))))
    assert len(calls) == 1


def test_a_small_image_is_tried_four_ways(calls):
    barcodes.decode(np.full((600, 800, 3), 255, np.uint8))
    assert len(calls) == 4  # two binarizers, then enlarged, then enlarged with contrast


def test_a_large_image_is_not_enlarged(calls):
    barcodes.decode(np.full((1800, 2400, 3), 255, np.uint8))
    assert len(calls) == 2
