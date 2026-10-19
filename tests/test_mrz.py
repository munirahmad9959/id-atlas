import pytest
from factories import TD1, TD2, TD3, make_td3

from id_atlas import mrz


def test_check_digit_icao_examples():
    assert mrz.check_digit("L898902C3") == 6
    assert mrz.check_digit("740812") == 2
    assert mrz.check_digit("<<<") == 0


def test_td3_parses_and_validates():
    result = mrz.read(TD3)
    assert result and result.format == "TD3" and result.valid
    assert result.surname == "ERIKSSON" and result.given_names == "ANNA MARIA"
    assert result.document_number == "L898902C3"
    assert result.birth_date == "1974-08-12" and result.expiry_date == "2012-04-15"
    assert result.sex == "F" and result.nationality == "UTO" and result.issuing_country == "UTO"
    assert result.personal_number == "ZE184226B" and all(result.checks.values())


def test_td1_parses_and_validates():
    result = mrz.read(TD1)
    assert result and result.format == "TD1" and result.valid
    assert result.document_number == "D23145890" and result.given_names == "ANNA MARIA"
    assert result.birth_date == "1974-08-12" and result.expiry_date == "2012-04-15"


def test_td2_parses_and_validates():
    result = mrz.read(TD2)
    assert result and result.format == "TD2" and result.valid
    assert result.document_code == "I" and result.issuing_country == "UTO" and result.nationality == "UTO"
    assert result.surname == "ERIKSSON" and result.given_names == "ANNA MARIA"
    assert result.document_number == "D23145890" and result.personal_number == ""
    assert result.birth_date == "1974-08-12" and result.expiry_date == "2012-04-15" and result.sex == "F"
    assert set(result.checks) == {"document_number", "birth_date", "expiry_date", "composite"}


def test_td2_is_not_mistaken_for_the_other_formats():
    assert mrz.read(TD3).format == "TD3" and mrz.read(TD1).format == "TD1"
    assert mrz.locate(TD2)[0] == "TD2"
    assert mrz.read([TD2[0]]) is None  # one line alone is not an MRZ


def test_td2_detects_a_corrupted_digit():
    result = mrz.read([TD2[0], TD2[1].replace("7408122", "7408123")])
    assert result and not result.valid and not result.checks["birth_date"]


def test_td2_optional_data_is_read_and_covered_by_the_composite_digit():
    cd = mrz.check_digit
    body = "D231458907UTO7408122F1204159AB12345"
    line2 = body + str(cd(body[0:10] + body[13:20] + body[21:35]))
    result = mrz.read([TD2[0], line2])
    assert result and result.valid and result.personal_number == "AB12345"
    assert not mrz.read([TD2[0], line2.replace("AB12345", "AB12346")]).valid


def test_td3_repairs_ocr_confusion_in_alphabetic_fields():
    # "UTO" read as "UT0": a digit in a country code is a misread letter.
    result = mrz.read([TD3[0], TD3[1].replace("UTO", "UT0")])
    assert result and result.nationality == "UTO" and result.valid


def test_td3_repairs_ocr_confusion_in_numeric_fields():
    # "740812" read with a letter O for the zero.
    result = mrz.read([TD3[0], TD3[1].replace("740812", "74O812")])
    assert result and result.birth_date == "1974-08-12" and result.valid


def test_names_repair_digits_misread_for_letters():
    # No check digit covers the name field, so a digit inside it can only be a misread letter.
    result = mrz.read(["P<UTOER1KSS0N<<ANNA<MAR1A<<<<<<<<<<<<<<<<<<<", TD3[1]])
    assert result and result.surname == "ERIKSSON" and result.given_names == "ANNA MARIA"


def test_filler_variants_are_normalised():
    noisy = [line.replace("<", "«") for line in TD3]
    result = mrz.read(noisy)
    assert result and result.valid and result.surname == "ERIKSSON"


def test_td3_pads_slightly_short_lines():
    result = mrz.read([TD3[0][:-3], TD3[1]])
    assert result and result.valid


def test_lines_too_far_off_length_are_not_an_mrz():
    assert mrz.read([TD3[0][:-20], TD3[1][:-20]]) is None
    # Ten characters short is close to a TD2 length: read as one, it can never pass its check digits.
    shortened = mrz.read([TD3[0][:-10], TD3[1][:-10]])
    assert shortened is None or not shortened.valid


def test_corrupted_digit_is_detected():
    result = mrz.read([TD3[0], TD3[1].replace("7408122", "7408123")])
    assert result and not result.valid
    assert (
        not result.checks["birth_date"] and result.checks["expiry_date"] and result.checks["document_number"]
    )


def test_bad_composite_digit_alone_invalidates():
    result = mrz.read([TD3[0], TD3[1][:-1] + "9"])
    assert result and not result.valid
    assert not result.checks["composite"] and result.checks["document_number"]


def test_ignores_non_mrz_text():
    assert mrz.read(["REPUBLICA DE COSTA RICA", "Nombre: ANA", "1 9999 9999"]) is None
    assert mrz.read([]) is None


def test_mrz_found_among_other_lines():
    result = mrz.read(["REPUBLICA DE COSTA RICA", "FLORES", *TD3, "2022"])
    assert result and result.valid


@pytest.mark.parametrize(
    "dob, expected",
    [("990101", "1999-01-01"), ("050101", "2005-01-01")],  # 99 can only be 1999; 05 is in the past as 2005
)
def test_birth_year_century(dob, expected):
    assert mrz.read(make_td3(dob=dob)).birth_date == expected


def test_expiry_is_always_this_century():
    assert mrz.read(make_td3(expiry="990101")).expiry_date == "2099-01-01"


def test_impossible_dates_are_none_not_errors():
    result = mrz.read(make_td3(dob="991399"))
    assert (
        result and result.birth_date is None and result.valid
    )  # checksum matches, the date is just impossible


@pytest.mark.parametrize("code, expected", [("M", "M"), ("F", "F"), ("<", "X"), ("X", "X"), ("Q", None)])
def test_sex_codes(code, expected):
    assert mrz.read(make_td3(sex=code)).sex == expected


def test_empty_personal_number_is_valid_with_filler_check_digit():
    result = mrz.read(make_td3())
    assert result and result.valid and result.personal_number == ""


def test_personal_number_is_checked_when_present():
    result = mrz.read(make_td3(personal="ABC123"))
    assert result and result.valid and result.personal_number == "ABC123"
    tampered = [result.lines[0], result.lines[1][:28] + "ABC124" + result.lines[1][34:]]
    broken = mrz.read(tampered)
    assert broken and not broken.checks["personal_number"] and not broken.valid
