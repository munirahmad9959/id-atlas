"""Pakistani National Identity Card (CNIC): classification, the parser and a full run. All fictional."""

import pytest
from factories import cnic_front, encode, line, stacked

from id_atlas import documents
from id_atlas.config import Settings
from id_atlas.countries import pakistan
from id_atlas.documents.fields import FIELD_NAMES
from id_atlas.engine import Line
from id_atlas.pipeline import extract_document


def cell(label: str, value: str | None, x: float, y: float) -> list[Line]:
    """A label with its value under it, as the card prints them. None leaves the value out."""
    lines = [line(label, x=x, y=y)]
    if value is not None:
        lines.append(line(value, x=x, y=y + 40))
    return lines


def card(**overrides) -> list[Line]:
    cells = {
        "Name": "Jane Sample",
        "Father Name": "John Sample",
        "Gender": "F",
        "Country of Stay": "Pakistan",
        "Identity Number": "00000-0000000-0",
        "Date of Birth": "01.01.1990",
        "Date of Issue": "01.02.2020",
        "Date of Expiry": "01.02.2030",
        **overrides,
    }
    places = {
        "Name": (30, 100),
        "Father Name": (30, 210),
        "Husband Name": (30, 210),
        "Gender": (30, 320),
        "Country of Stay": (330, 320),
        "Identity Number": (30, 430),
        "Date of Birth": (430, 430),
        "Date of Issue": (30, 540),
        "Date of Expiry": (430, 540),
    }
    lines = [line("PAKISTAN", y=20), line("National Identity Card", x=420, y=20)]
    for label, value in cells.items():
        if value != "OMIT":
            lines += cell(label, value, *places[label])
    return lines


def values(lines: list[Line]) -> dict[str, str | None]:
    return {k: v.value for k, v in pakistan.parse_cnic(lines).items()}


# --- classification -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texts, expected",
    [
        (["PAKISTAN", "National Identity Card"], "cnic"),
        (["national identity card"], "cnic"),  # case is irrelevant
        (["NationalIdentityCard"], "cnic"),  # the OCR sometimes drops the spaces
        (["PAKISTAN", "ISLAMIC REPUBLIC OF PAKISTAN"], "unknown"),  # the passport prints these too
        (["Hello", "world"], "unknown"),
    ],
)
def test_classify_cnic(texts, expected):
    assert documents.classify(stacked(*texts), None) == expected


def test_the_registered_spec():
    spec = documents.get("cnic")
    assert spec.country == "PAK" and spec.verified and not spec.two_sided
    assert spec.required == ("document_number", "full_name", "birth_date", "expiry_date")


# --- the parser ---------------------------------------------------------------------------------


def test_front_as_printed():
    fields = pakistan.parse_cnic(card())
    assert {k: v.value for k, v in fields.items()} == {
        "full_name": "Jane Sample",
        "father_name": "John Sample",
        "sex": "F",
        "country_of_stay": "Pakistan",
        "document_number": "0000000000000",
        "birth_date": "1990-01-01",
        "issue_date": "2020-02-01",
        "expiry_date": "2030-02-01",
    }
    assert fields["document_number"].raw == "00000-0000000-0"


def test_a_husband_name_is_read_in_place_of_the_fathers():
    result = values(card(**{"Father Name": "OMIT", "Husband Name": "Jack Sample"}))
    assert result["husband_name"] == "Jack Sample" and "father_name" not in result
    assert result["full_name"] == "Jane Sample"


def test_a_fathers_name_leaves_the_husband_field_empty():
    assert "husband_name" not in values(card())


def test_the_two_columns_are_told_apart():
    # Gender and Country of Stay share a row, and so do the birth and expiry dates.
    result = values(card(Gender="M", **{"Country of Stay": "Testland"}))
    assert result["sex"] == "M" and result["country_of_stay"] == "Testland"
    assert result["birth_date"] == "1990-01-01" and result["expiry_date"] == "2030-02-01"


def test_a_merged_label_line_still_gives_each_label_its_own_value():
    # The OCR sometimes returns "Gender Country of Stay" as one line; each value sits under its own part.
    lines = [
        Line("Gender Country of Stay", 0.99, 200, 240, 330, 24),
        Line("M", 0.99, 206, 270, 24, 24),
        Line("Testland", 0.99, 380, 270, 120, 24),
    ]
    assert values(lines) == {"sex": "M", "country_of_stay": "Testland"}


def test_a_misread_country_label_is_still_found():
    lines = [line("Cauntry of Stay", x=330, y=320), line("Testland", x=330, y=360)]
    assert values(lines) == {"country_of_stay": "Testland"}


def test_a_name_label_does_not_take_the_father_name_label():
    lines = [line("Father Name", y=100), line("John Sample", y=140)]
    assert values(lines) == {"father_name": "John Sample"}


def test_a_value_on_the_same_line_as_its_label():
    assert values([line("Date of Birth: 01.01.1990")]) == {"birth_date": "1990-01-01"}


@pytest.mark.parametrize("label", ["Name", "Father Name", "Gender", "Country of Stay", "Date of Birth"])
def test_a_label_with_no_value_gives_a_missing_field(label):
    result = values(card(**{label: None}))
    key = {
        "Name": "full_name",
        "Father Name": "father_name",
        "Gender": "sex",
        "Country of Stay": "country_of_stay",
        "Date of Birth": "birth_date",
    }[label]
    assert key not in result  # never the next cell's value
    assert len(result) == 7


def test_a_missing_number_label_does_not_matter():
    unlabeled = card(**{"Identity Number": "OMIT"}) + [line("00000-0000000-0", x=30, y=475)]
    assert values(unlabeled)["document_number"] == "0000000000000"
    assert "document_number" in values(card(**{"Identity Number": "00000 0000000 0"}))


@pytest.mark.parametrize("number", ["0000-0000000-0", "00000-000000-0", "00000-0000000", "ABCDE-FGHIJKL-M"])
def test_things_that_are_not_an_identity_number(number):
    assert "document_number" not in values(card(**{"Identity Number": number}))


def test_urdu_noise_is_not_a_name():
    lines = [line("Name", y=100), line("1 ^ 7 ~", y=140), line("Father Name", y=210), line("John", y=250)]
    assert values(lines) == {"father_name": "John"}


@pytest.mark.parametrize("sex", ["m", "F", "X"])
def test_sex_values(sex):
    assert values(card(Gender=sex))["sex"] == sex.upper()


def test_anything_else_is_not_a_sex():
    assert "sex" not in values(card(Gender="Pakistan"))


def test_an_impossible_date_is_invalid_not_dropped():
    fields = pakistan.parse_cnic(card(**{"Date of Expiry": "31.02.2030"}))
    assert fields["expiry_date"].value is None and fields["expiry_date"].raw == "31.02.2030"


def test_confidence_comes_from_the_line_that_holds_the_value():
    lines = [line("Name", y=100), line("Jane Sample", y=140, score=0.42)]
    assert pakistan.parse_cnic(lines)["full_name"].confidence == 0.42


def test_nothing_found_means_no_fields():
    assert pakistan.parse_cnic(stacked("Hello", "world")) == {}
    assert pakistan.parse_cnic([]) == {}


def test_only_canonical_field_names_are_produced():
    produced = set(pakistan.parse_cnic(card(**{"Father Name": "OMIT", "Husband Name": "Jack Sample"})))
    assert produced <= set(FIELD_NAMES) and set(documents.get("cnic").required) <= produced


# --- a full run ---------------------------------------------------------------------------------


def run(image) -> object:
    return extract_document(encode(image), None, Settings())


def test_full_pipeline_on_a_synthetic_card():
    result = run(cnic_front())
    assert result.document_type == "cnic" and result.country == "PAK"
    assert {k: v.value for k, v in result.fields.items()} == {
        "full_name": "Jane Sample",
        "father_name": "John Sample",
        "sex": "F",
        "country_of_stay": "Pakistan",
        "document_number": "0000000000000",
        "birth_date": "1990-01-01",
        "issue_date": "2020-02-01",
        "expiry_date": "2030-02-01",
    }
    # One side is enough and the parser is verified, so a complete card needs no review.
    assert result.review_reasons == []


def test_full_pipeline_with_a_husband_name_and_a_label_with_no_value():
    result = run(cnic_front(parent_label="Husband Name", parent="Jack Sample", gender=None))
    assert result.fields["husband_name"].value == "Jack Sample"
    assert "father_name" not in result.fields and "sex" not in result.fields
    assert result.fields["country_of_stay"].value == "Pakistan"


def test_full_pipeline_flags_a_missing_required_field():
    result = run(cnic_front(birth=None))
    assert "birth_date" not in result.fields
    assert "missing:birth_date" in result.review_reasons
