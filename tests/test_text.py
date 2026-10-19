"""The language-neutral text helpers: dates, label detection, folding. Costa Rican wording is tested in
test_documents.py; everything here uses English or a style defined in the test."""

import pytest
from factories import stacked

from id_atlas import documents
from id_atlas.documents.text import Reader, Style, fold_confusables, parse_date

# --- dates --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, iso",
    [
        ("02.03.1991", "1991-03-02"),
        ("15.06.2018", "2018-06-15"),
        ("12 JAN 1990", "1990-01-12"),
        ("12-Oct-2030", "2030-10-12"),
        ("09 OCTOBER 2033", "2033-10-09"),
        ("21 JUL 2003", "2003-07-21"),
        ("1 dec 2020", "2020-12-01"),
        ("1990-01-12", "1990-01-12"),
        ("1990/1/2", "1990-01-02"),
        ("Date of Expiry 05/03/2030", "2030-03-05"),
    ],
)
def test_dates_with_the_default_style(text, iso):
    assert parse_date(text)[0] == iso


def test_spanish_is_only_understood_when_the_style_says_so():
    assert parse_date("12 ENE 1990")[0] is None  # an unknown month is present but has no value
    assert parse_date("12 ENE 1990")[1] == "12 ENE 1990"
    assert parse_date("12 ENE 1990", Style(months={"ENE": 1}))[0] == "1990-01-12"


def test_joiner_words_are_only_accepted_when_the_style_lists_them():
    assert parse_date("5 de MAR de 2030") is None
    assert parse_date("5 de MAR de 2030", Style(date_joiners=("DE",)))[0] == "2030-03-05"


def test_month_first_is_opt_in():
    assert parse_date("03/04/2030")[0] == "2030-04-03"
    assert parse_date("03/04/2030", Style(month_first=True))[0] == "2030-03-04"
    assert parse_date("31/01/2030", Style(month_first=True))[0] is None  # there is no month 31
    assert parse_date("04 MAR 2030", Style(month_first=True))[0] == "2030-03-04"  # a name is never ambiguous


@pytest.mark.parametrize("text", ["1998-13-01", "1998-02-30", "00.00.0000"])
def test_impossible_dates_keep_their_text_but_have_no_value(text):
    value, raw = parse_date(text)
    assert value is None and raw


@pytest.mark.parametrize("text", ["00000-0000000-0", "1 9999 9999", "199999999", "12/01/90", "", "2016"])
def test_numbers_and_partial_dates_are_not_dates(text):
    assert parse_date(text) is None


# --- finding the value after a label ------------------------------------------------------------

ENGLISH = Style(label_words=r"NAME|GENDER|DATE\s+OF|IDENTITY\s+NUMBER")


def test_a_neighbouring_label_is_not_taken_as_a_value_once_the_style_knows_its_words():
    lines = stacked("Name", "Father Name", "John Sample")  # the holder's own name was not read
    assert Reader(lines, ENGLISH).text_after(r"^Name") is None
    # Without label words the next line is handed over, which is the bug the style prevents.
    assert Reader(lines).text_after(r"^Name").value == "Father Name"


def test_a_value_on_the_same_line_or_the_line_below_is_found():
    assert Reader(stacked("Name: Jane Sample"), ENGLISH).text_after(r"^Name").value == "Jane Sample"
    assert Reader(stacked("Gender", "M"), ENGLISH).text_after("Gender").value == "M"


def test_a_line_that_is_only_a_label_is_never_a_value_in_any_language():
    lines = stacked("Name", "Père:")  # a trailing colon is enough, accents and all
    assert Reader(lines).text_after(r"^Name") is None


def test_date_after_a_label_uses_the_style():
    lines = stacked("Date of Birth", "12.01.1990")
    field = Reader(lines, ENGLISH).date_after(r"DATE\s+OF\s+BIRTH")
    assert field.value == "1990-01-12" and field.raw == "12.01.1990"


# --- folding and the passport fallback ----------------------------------------------------------


def test_look_alike_characters_fold_together():
    assert fold_confusables("Cl-123 456") == fold_confusables("C1123456") == "C1123456"
    assert fold_confusables("B1") == fold_confusables("81")
    assert fold_confusables("CI-1") != fold_confusables("XX-1")


@pytest.mark.parametrize("word", ["PASSPORT", "Pasaporte", "PASSEPORT", "Passaporto", "REISEPASS"])
def test_a_passport_page_without_an_mrz_is_recognised_in_several_languages(word):
    assert documents.classify(stacked(word), None) == "passport"
