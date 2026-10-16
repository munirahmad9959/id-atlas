import io

import cv2
import numpy as np
import pytest
from factories import bgr, card_image, encode
from PIL import Image

from id_atlas import imaging

PAGE = bgr(card_image("REPUBLICA DE COSTA RICA", "Nombre: ANA MARIA", "Vence: 05/03/2030"))


# --- decoding uploads ---------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP", "BMP"])
def test_common_formats_decode_to_rgb(fmt):
    img = imaging.open_image(encode(card_image("x", size=(120, 80)), fmt))
    assert img.mode == "RGB" and img.size == (120, 80)


@pytest.mark.parametrize("mode", ["L", "RGBA", "P", "CMYK"])
def test_other_color_modes_are_converted(mode):
    source = Image.new("RGB", (40, 30), "red").convert(mode)
    buffer = io.BytesIO()
    source.save(buffer, "TIFF" if mode == "CMYK" else "PNG")
    assert imaging.open_image(buffer.getvalue()).mode == "RGB"


def test_exif_orientation_is_applied():
    exif = Image.Exif()
    exif[274] = 6  # "rotate 90 degrees clockwise to display": how a phone stores a portrait photo
    landscape = Image.new("RGB", (200, 100), "white")
    data = encode(landscape, "JPEG", exif=exif)
    assert imaging.open_image(data).size == (100, 200)


@pytest.mark.parametrize("data", [b"", b"not an image", b"\x89PNG\r\n\x1a\n" + b"\x00" * 20])
def test_unreadable_bytes_raise_invalid_image(data):
    with pytest.raises(imaging.InvalidImage, match="not a readable image"):
        imaging.open_image(data)


def test_a_truncated_file_raises_invalid_image():
    data = encode(card_image("some text"), "PNG")
    with pytest.raises(imaging.InvalidImage):
        imaging.open_image(data[: len(data) // 2])


# --- converting to what the OCR takes -----------------------------------------------------------


def test_channels_are_reordered_to_bgr():
    red = imaging.to_bgr(Image.new("RGB", (4, 4), (255, 0, 0)), 100)
    assert red.dtype == np.uint8 and red.flags["C_CONTIGUOUS"]
    assert tuple(red[0, 0]) == (0, 0, 255)


def test_large_images_are_shrunk_keeping_their_proportions():
    original = Image.new("RGB", (4000, 2000), "white")
    small = imaging.to_bgr(original, 1000)
    assert small.shape[:2] == (500, 1000)
    assert original.size == (4000, 2000)  # the caller's image is untouched


@pytest.mark.parametrize("size", [(800, 600), (1000, 1000)])
def test_small_images_are_left_alone(size):
    assert imaging.to_bgr(Image.new("RGB", size, "white"), 1000).shape[:2] == (size[1], size[0])


def test_load_image_decodes_and_limits_in_one_step():
    data = encode(Image.new("RGB", (3000, 1500), "white"))
    assert imaging.load_image(data, 1500).shape[:2] == (750, 1500)
    with pytest.raises(imaging.InvalidImage):
        imaging.load_image(b"junk", 1500)


# --- recognising the same picture twice ---------------------------------------------------------


@pytest.mark.parametrize(
    "variant",
    [
        pytest.param(lambda a: a.copy(), id="identical"),
        pytest.param(
            lambda a: cv2.resize(a, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA), id="rescaled"
        ),
        pytest.param(lambda a: cv2.convertScaleAbs(a, alpha=1, beta=25), id="brighter"),
        pytest.param(
            lambda a: cv2.imdecode(cv2.imencode(".jpg", a, [cv2.IMWRITE_JPEG_QUALITY, 60])[1], 1),
            id="recompressed",
        ),
    ],
)
def test_copies_of_one_photo_are_the_same_picture(variant):
    assert imaging.same_picture(PAGE, variant(PAGE))


@pytest.mark.parametrize(
    "other",
    [
        pytest.param(bgr(card_image(background=(60, 140, 90))), id="green-card-vs-white-page"),
        pytest.param(bgr(card_image("x", background=(20, 20, 20))), id="dark-page"),
        pytest.param(cv2.flip(PAGE, 0), id="upside-down"),
    ],
)
def test_clearly_different_pictures_are_not(other):
    assert not imaging.same_picture(PAGE, other)


def test_it_does_not_care_about_the_pictures_size():
    assert imaging.same_picture(PAGE, cv2.resize(PAGE, (300, 120)))
