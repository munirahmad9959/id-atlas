"""End to end: synthetic documents (see factories) through the real OCR, MRZ and barcode code."""

import pytest
from factories import (
    card_image,
    cedula_back,
    cedula_front,
    encode,
    license_back,
    license_front,
    make_td3,
    passport_page,
)
from PIL import Image

from id_atlas import pipeline
from id_atlas.config import Settings
from id_atlas.imaging import InvalidImage
from id_atlas.pipeline import extract, extract_document
from id_atlas.schemas import Field

CEDULA_FRONT = encode(cedula_front())
CEDULA_BACK = encode(cedula_back())
LICENSE_FRONT = encode(license_front())
LICENSE_BACK = encode(license_back())
BLANK = encode(Image.new("RGB", (580, 360), "white"))


def settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def read(front, back=None, hint=None, **overrides):
    return extract_document(front, back, settings(**overrides), hint)


def values(result) -> dict[str, str | None]:
    return {name: field.value for name, field in result.fields.items()}


@pytest.fixture(scope="module")
def cedula():
    return read(CEDULA_FRONT, CEDULA_BACK)


@pytest.fixture(scope="module")
def licence():
    return read(LICENSE_FRONT, LICENSE_BACK)


# --- a complete, clean document -----------------------------------------------------------------


def test_a_complete_cedula_needs_no_review(cedula):
    assert cedula.document_type == "cedula"
    assert cedula.review_reasons == [] and cedula.needs_review is False
    assert values(cedula) == {
        "given_names": "ANA MARIA",
        "surname": "PRUEBA",
        "second_surname": "MUESTRA",
        "birth_date": "1990-01-12",
        "expiry_date": "2030-03-05",
        "document_number": "199999999",
    }


def test_the_result_describes_both_sides(cedula):
    assert [(s.side, s.document_type) for s in cedula.sides] == [("front", "cedula"), ("back", "cedula")]
    assert all(s.fields_found > 0 for s in cedula.sides)
    assert cedula.mrz is None and isinstance(cedula.elapsed_ms, int) and cedula.elapsed_ms >= 0


def test_the_barcode_on_the_back_is_returned(cedula):
    assert cedula.barcodes == ["TEST-PAYLOAD-123456"]


def test_parents_birthplace_and_address_never_reach_the_result(cedula):
    everything = repr(cedula.model_dump())
    for private in ("PEDRO", "MARIA PRUEBA", "San José", "Calle 1"):
        assert private not in everything


def test_a_complete_license_is_flagged_only_because_its_template_is_unvalidated(licence):
    assert licence.document_type == "driver_license"
    assert licence.review_reasons == ["template_unverified"]
    assert [s.document_type for s in licence.sides] == ["driver_license", "driver_license"]


def test_the_license_barcode_confirms_and_replaces_the_printed_text(licence):
    assert licence.barcodes == ["CI123456789B1"]
    # The OCR may read the letter I as an l; the machine-read barcode text is what ends up in the result.
    assert licence.fields["document_number"].value == "CI-123456789"
    assert licence.fields["license_category"].value == "B1"
    assert (
        licence.fields["document_number"].confidence == licence.fields["license_category"].confidence == 0.99
    )


# --- combining the two sides --------------------------------------------------------------------


def test_a_valid_value_beats_an_unreadable_one():
    result = read(encode(cedula_front(birth="00/00/0000")), CEDULA_BACK)
    assert result.fields["birth_date"].value == "1990-01-12" and result.fields["birth_date"].side == "back"
    assert result.fields["document_number"].side == "front"
    assert result.review_reasons == []


def test_the_front_wins_a_disagreement_and_the_conflict_is_flagged():
    result = read(CEDULA_FRONT, encode(cedula_back(birth="13/01/1990")))
    assert result.fields["birth_date"].value == "1990-01-12" and result.fields["birth_date"].side == "front"
    assert result.review_reasons == ["field_conflict:birth_date"]


def test_conflicting_numbers_between_the_sides_are_flagged():
    result = read(CEDULA_FRONT, encode(cedula_back(number="2-3333-4444")))
    assert "field_conflict:document_number" in result.review_reasons
    assert result.fields["document_number"].value == "199999999"  # the front's


def test_a_blank_back_is_not_a_problem():
    result = read(CEDULA_FRONT, BLANK)
    assert result.document_type == "cedula" and result.review_reasons == []
    assert [s.document_type for s in result.sides] == ["cedula", "unknown"]


# --- problems with the sides --------------------------------------------------------------------


@pytest.mark.parametrize("front", [CEDULA_FRONT, LICENSE_FRONT], ids=["cedula", "license"])
def test_a_missing_back_is_flagged_for_two_sided_documents(front):
    assert "missing_back_side" in read(front).review_reasons


def test_a_passport_needs_no_back():
    assert "missing_back_side" not in read(encode(passport_page(make_td3()))).review_reasons


def test_a_single_image_is_never_flagged_for_a_missing_back():
    result = extract(CEDULA_FRONT, settings())
    assert result.document_type == "cedula" and result.review_reasons == []


@pytest.mark.parametrize(
    "front, back",
    [(CEDULA_BACK, CEDULA_FRONT), (LICENSE_BACK, LICENSE_FRONT)],
    ids=["cedula", "license"],
)
def test_swapped_sides_are_flagged(front, back):
    assert "sides_possibly_swapped" in read(front, back).review_reasons


def test_sides_of_different_documents_are_flagged():
    assert "sides_mismatch" in read(CEDULA_FRONT, LICENSE_BACK).review_reasons


def test_the_same_picture_twice_is_flagged():
    assert "duplicate_sides" in read(CEDULA_FRONT, CEDULA_FRONT).review_reasons


# --- the license barcode ------------------------------------------------------------------------


def test_a_barcode_that_disagrees_is_flagged_and_does_not_overwrite():
    result = read(encode(license_front(barcode_text="CI123456789B2")), LICENSE_BACK)
    assert "barcode_mismatch:license_category" in result.review_reasons
    assert result.fields["license_category"].value == "B1"


def test_a_license_without_a_barcode_is_read_from_its_text():
    result = read(encode(license_front(barcode_text=None)), LICENSE_BACK)
    assert result.barcodes == [] and result.review_reasons == ["template_unverified"]
    assert result.fields["document_number"].value.upper().replace("L", "I") == "CI-123456789"


# --- detection and hints ------------------------------------------------------------------------


def test_a_page_of_unrelated_text_is_unknown():
    result = read(encode(card_image("Hello there", "nothing to see here")))
    assert result.document_type == "unknown" and result.fields == {} and result.mrz is None
    assert result.review_reasons == ["unknown_document_type"]


def test_a_hint_overrides_detection():
    result = read(CEDULA_FRONT, None, hint="dimex")
    assert result.document_type == "dimex"
    assert {"template_unverified", "missing:document_number"} <= set(result.review_reasons)


# --- passports ----------------------------------------------------------------------------------


def test_a_passport_is_read_from_its_mrz():
    result = read(encode(passport_page(make_td3())))
    assert result.document_type == "passport" and result.mrz.valid and result.mrz.format == "TD3"
    assert result.review_reasons == []
    assert values(result)["surname"] == "PRUEBA" and values(result)["birth_date"] == "1990-01-01"
    assert {f.side for f in result.fields.values()} == {"front"}


def test_a_tampered_mrz_is_flagged_and_its_fields_lose_confidence():
    lines = make_td3()
    lines[1] = lines[1].replace("9001011", "9001012")  # the birth date no longer matches its check digit
    result = read(encode(passport_page(lines)))
    assert "mrz_checksum_failed" in result.review_reasons
    assert result.fields["birth_date"].confidence == 0.5


# --- phone-photo conditions ---------------------------------------------------------------------


def test_upside_down_and_sideways_photos_are_read():
    upside_down = encode(cedula_front().rotate(180))
    sideways = encode(cedula_back().rotate(90, expand=True))
    result = read(upside_down, sideways)
    assert result.document_type == "cedula" and result.review_reasons == []
    assert (
        result.fields["document_number"].value == "199999999"
        and result.fields["birth_date"].value == "1990-01-12"
    )


def test_an_upload_stored_rotated_with_exif_is_turned_upright():
    exif = Image.Exif()
    exif[274] = 6  # a portrait phone photo: stored sideways, displayed rotated 90 degrees clockwise
    stored = cedula_front().rotate(90, expand=True)
    result = read(encode(stored, "JPEG", exif=exif), CEDULA_BACK)
    assert result.review_reasons == [] and result.fields["given_names"].value == "ANA MARIA"


def test_large_photos_still_read_text_and_barcode():
    big = license_front().resize(
        (2700, int(2700 * license_front().height / license_front().width)), Image.LANCZOS
    )
    result = read(encode(big, "JPEG", quality=90), LICENSE_BACK)
    assert result.barcodes == ["CI123456789B1"] and result.fields["license_category"].value == "B1"


# --- unreadable input ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "front, back, side",
    [(b"junk", CEDULA_BACK, "front"), (CEDULA_FRONT, b"junk", "back"), (b"", None, "front")],
)
def test_an_unreadable_image_names_its_side(front, back, side):
    with pytest.raises(InvalidImage, match=f"^{side}: not a readable image$"):
        read(front, back)


# --- review rules (no images) -------------------------------------------------------------------


def field(value="x", confidence=0.99) -> Field:
    return Field(value=value, raw=value, confidence=confidence)


@pytest.mark.parametrize(
    "doc_type, fields, expected",
    [
        ("unknown", {}, ["unknown_document_type"]),
        ("dimex", {"document_number": field()}, ["template_unverified"]),
        (
            "driver_license",
            {"document_number": field(), "expiry_date": field(), "license_category": field()},
            ["template_unverified"],
        ),
        ("dimex", {}, ["template_unverified", "missing:document_number"]),
        ("dimex", {"document_number": field(None)}, ["template_unverified", "invalid:document_number"]),
        (
            "dimex",
            {"document_number": field(confidence=0.5)},
            ["template_unverified", "low_confidence:document_number"],
        ),
        (
            "dimex",
            {"document_number": field(confidence=0.85)},
            ["template_unverified"],
        ),  # exactly at the threshold passes
    ],
)
def test_review_reasons(doc_type, fields, expected):
    assert pipeline._review_reasons(doc_type, fields, None, settings()) == expected


def test_the_review_threshold_is_configurable():
    fields = {"document_number": field(confidence=0.7)}
    assert "low_confidence:document_number" in pipeline._review_reasons("dimex", fields, None, settings())
    assert "low_confidence:document_number" not in pipeline._review_reasons(
        "dimex", fields, None, settings(review_below=0.6)
    )


def test_the_country_comes_from_the_document_or_its_mrz():
    cedula = pipeline.extract_document(encode(cedula_front()), None, settings())
    assert cedula.country == "CRI"
    passport = pipeline.extract(encode(passport_page(make_td3(nationality="CRI"))), settings())
    assert passport.document_type == "passport" and passport.country == "CRI"
    assert pipeline.extract(encode(card_image("hello", "world")), settings()).country is None
