import pytest

from id_atlas import mrz

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
    assert mrz.read([TD3[0][:-10], TD3[1][:-10]]) is None


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
