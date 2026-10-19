import pytest
from factories import TD1, TD3, line, make_td3, stacked

from id_atlas import documents, mrz
from id_atlas.countries import costa_rica
from id_atlas.documents.text import parse_date
from id_atlas.schemas import Field

# --- classification -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texts, expected",
    [
        (["REPÚBLICA DE COSTA RICA", "CÉDULA DE IDENTIDAD"], "cedula"),
        (["cedula de identidad"], "cedula"),  # case and accents are irrelevant
        (["CEDULADEIDENTIDAD"], "cedula"),  # the OCR sometimes drops the spaces
        (["TRIBUNAL SUPREMO DE ELECCIONES"], "cedula"),
        (["Domicilio Electoral: Calle 1", "Nombre del Padre: PEDRO"], "cedula"),  # the back side alone
        (["Licencia de Conducir"], "driver_license"),
        (["EDUCACIÓN VIAL", "COSEVI"], "driver_license"),  # the back side alone
        (["COSEVI Seguridad Vial"], "driver_license"),
        (["DIMEX", "Documento de Identidad Migratorio"], "dimex"),
        (["PASAPORTE / PASSPORT"], "passport"),
        (["Hello", "world"], "unknown"),
        ([], "unknown"),
    ],
)
def test_classify_by_text(texts, expected):
    assert documents.classify(stacked(*texts), None) == expected


def test_classify_uses_the_mrz_when_no_words_match():
    assert documents.classify([], mrz.read(TD3)) == "passport"
    assert documents.classify([], mrz.read(TD1)) == "id_mrz"


def test_words_beat_the_mrz():
    assert documents.classify(stacked("CÉDULA DE IDENTIDAD"), mrz.read(TD1)) == "cedula"


@pytest.mark.parametrize(
    "texts, expected",
    [
        (["CÉDULA DE IDENTIDAD", "Nombre: ANA"], "front"),
        (["Domicilio Electoral: Calle 1"], "back"),
        (["Nombre de la Madre: ANA"], "back"),
        (["Licencia de Conducir"], "front"),
        (["CLASIFICACIÓN", "MOTOCICLETAS"], "back"),
        (["CÉDULA DE IDENTIDAD", "Domicilio Electoral"], None),  # both sides at once: cannot tell
        (["COSEVI"], None),  # recognisable, but printed on neither side exclusively
        (["Hello"], None),
    ],
)
def test_side_guess(texts, expected):
    assert documents.side_guess(stacked(*texts)) == expected


# --- dates --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, iso",
    [
        ("12-01-1990", "1990-01-12"),
        ("12 01 1990", "1990-01-12"),
        ("12/01/1990", "1990-01-12"),
        ("12.01.1990", "1990-01-12"),
        ("1/2/1990", "1990-02-01"),
        ("12 ENE 1990", "1990-01-12"),
        ("12-ene-1990", "1990-01-12"),
        ("5 de setiembre de 2030", "2030-09-05"),
        ("5 DE SEPTIEMBRE DE 2030", "2030-09-05"),
        ("Vence: 05/03/2030", "2030-03-05"),  # surrounding text is ignored
    ],
)
def test_dates_in_every_supported_format(text, iso):
    assert parse_date(text)[0] == iso


def test_every_spanish_month_is_understood():
    names = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]
    assert [parse_date(f"10 {n} 2020")[0] for n in names] == [f"2020-{m:02d}-10" for m in range(1, 13)]
    assert parse_date("10 AGOSTO 2020")[0] == "2020-08-10"


@pytest.mark.parametrize("text", ["00-00-0000", "31 02 1990", "12 XYZ 1990", "32/01/1990"])
def test_impossible_dates_keep_their_text_but_have_no_value(text):
    value, raw = parse_date(text)
    assert value is None and raw


@pytest.mark.parametrize("text", ["no date here", "1 9999 9999", "12/01/90", "", "199999999"])
def test_things_that_are_not_dates(text):
    assert parse_date(text) is None


# --- cédula -------------------------------------------------------------------------------------


def test_cedula_front_as_printed():
    fields = costa_rica.parse_cedula(
        stacked(
            "1 9999 9999",
            "Nombre: ANA MARIA",
            "1ºApellido: PRUEBA",
            "2ºApellido: MUESTRA",
            "F. Nac: 12/01/1990 Vence: 05/03/2030",
        )
    )
    assert {k: v.value for k, v in fields.items()} == {
        "id_number": "199999999",
        "given_names": "ANA MARIA",
        "surname1": "PRUEBA",
        "surname2": "MUESTRA",
        "birth_date": "1990-01-12",
        "expiry_date": "2030-03-05",
    }
    assert fields["id_number"].raw == "1 9999 9999"


def test_cedula_back_with_labels():
    fields = costa_rica.parse_cedula(
        stacked(
            "Número de Cédula: 1-9999-9999",
            "Fecha de Nacimiento: 12 ENE 1990",
            "Lugar de Nacimiento: San José",
            "Nombre del Padre: PEDRO PRUEBA",
            "Nombre de la Madre: MARIA PRUEBA",
            "Domicilio Electoral: Calle 1",
            "Vencimiento: 05/03/2030",
        )
    )
    assert {k: v.value for k, v in fields.items()} == {
        "id_number": "199999999",
        "birth_date": "1990-01-12",
        "expiry_date": "2030-03-05",
    }


def test_parents_birthplace_and_address_are_never_extracted():
    fields = costa_rica.parse_cedula(
        stacked(
            "Nombre del Padre: PEDRO",
            "Nombre de la Madre: MARIA",
            "Lugar de Nacimiento: X",
            "Domicilio Electoral: Y",
        )
    )
    assert fields == {}


def test_value_on_the_line_below_the_label():
    fields = costa_rica.parse_cedula(
        stacked("Fecha de Nacimiento:", "12/01/1990", "Vencimiento:", "05/03/2030")
    )
    assert fields["birth_date"].value == "1990-01-12" and fields["expiry_date"].value == "2030-03-05"


def test_value_to_the_right_of_the_label():
    lines = [
        line("Nombre:", x=30, y=100),
        line("ANA", x=200, y=102),
        line("1ºApellido:", x=30, y=140),
        line("PRUEBA", x=200, y=141),
    ]
    fields = costa_rica.parse_cedula(lines)
    assert fields["given_names"].value == "ANA" and fields["surname1"].value == "PRUEBA"


def test_a_label_is_not_mistaken_for_the_next_labels_value():
    # The date is missing: the next row is another label, which must not be taken as the value.
    fields = costa_rica.parse_cedula(stacked("Fecha de Nacimiento:", "Vencimiento:", "05/03/2030"))
    assert "birth_date" not in fields and fields["expiry_date"].value == "2030-03-05"


def test_a_missing_name_does_not_borrow_the_next_rows_value():
    fields = costa_rica.parse_cedula(stacked("Nombre:", "1ºApellido: PRUEBA", "2ºApellido: MUESTRA"))
    assert "given_names" not in fields
    assert fields["surname1"].value == "PRUEBA" and fields["surname2"].value == "MUESTRA"


def test_a_missing_value_does_not_borrow_across_a_gap_either():
    fields = costa_rica.parse_cedula(stacked("Vencimiento:", "Domicilio Electoral: Calle 1"))
    assert "expiry_date" not in fields


def test_placeholder_dates_are_present_but_unparsed():
    fields = costa_rica.parse_cedula(stacked("F. Nac: 00/00/0000 Vence: 00/00/0000"))
    assert fields["birth_date"].value is None and fields["birth_date"].raw == "00/00/0000"
    assert fields["expiry_date"].value is None


def test_field_confidence_comes_from_the_line_that_holds_the_value():
    lines = [line("Nombre:", y=100, score=0.99), line("ANA", x=200, y=100, score=0.61)]
    assert costa_rica.parse_cedula(lines)["given_names"].confidence == 0.61


@pytest.mark.parametrize("text", ["099999999", "1 9999 99999", "12 345", "tel 8888-8888", "1999999999"])
def test_things_that_are_not_a_cedula_number(text):
    assert "id_number" not in costa_rica.parse_cedula(stacked(text))


def test_nothing_found_means_no_fields():
    assert costa_rica.parse_cedula(stacked("Hello", "world")) == {}
    assert costa_rica.parse_cedula([]) == {}


# --- driver's license ---------------------------------------------------------------------------


def test_license_front():
    fields = costa_rica.parse_license(
        stacked(
            "REPUBLICA DE COSTA RICA",
            "Licencia de Conducir",
            "N°:",
            "CI-123456789",
            "Expedición 01-02-2020",
            "Nacimiento 12-01-1990",
            "Vencimiento 01-02-2030",
            "Tipo: B1",
        )
    )
    assert {k: v.value for k, v in fields.items()} == {
        "license_number": "CI-123456789",
        "issue_date": "2020-02-01",
        "birth_date": "1990-01-12",
        "expiry_date": "2030-02-01",
        "license_type": "B1",
    }


def test_license_number_without_a_dash_and_other_types():
    fields = costa_rica.parse_license(stacked("CI123456789", "Tipo: A"))
    assert fields["license_number"].value == "CI123456789" and fields["license_type"].value == "A"


def test_license_missing_pieces_are_absent():
    assert costa_rica.parse_license(stacked("Licencia de Conducir")) == {}


# --- DIMEX --------------------------------------------------------------------------------------


@pytest.mark.parametrize("number", ["155812345678", "15581234567"])
def test_dimex_number_has_eleven_or_twelve_digits(number):
    assert costa_rica.parse_dimex(stacked("DIMEX", number))["id_number"].value == number


@pytest.mark.parametrize("text", ["1558123456", "1558123456789", "no number"])
def test_dimex_rejects_other_lengths(text):
    assert costa_rica.parse_dimex(stacked(text)) == {}


# --- license barcode cross-check ----------------------------------------------------------------


def license_fields(number="CI-000000000", kind="B1", kind_confidence=0.78) -> dict[str, Field]:
    return {
        "license_number": Field(value=number, raw=number, confidence=0.97, side="front"),
        "license_type": Field(value=kind, raw=kind, confidence=kind_confidence, side="front"),
    }


def test_matching_barcode_raises_confidence():
    fields, reasons = costa_rica.reconcile_license_barcode(license_fields(), ["CI000000000B1"])
    assert reasons == []
    assert fields["license_type"].confidence == 0.99 and fields["license_number"].confidence == 0.99


@pytest.mark.parametrize(
    "printed_number, printed_kind",
    [
        ("Cl-123456789", "B1"),
        ("C1-123456789", "B1"),
        ("CI-I23456789", "B1"),
        ("CI-123456789", "81"),
        ("CI123456789", "B1"),
    ],
    ids=["I-read-as-l", "I-read-as-1", "1-read-as-I", "B-read-as-8", "dash-missing"],
)
def test_ocr_letter_confusions_still_agree_with_the_barcode(printed_number, printed_kind):
    fields, reasons = costa_rica.reconcile_license_barcode(
        license_fields(number=printed_number, kind=printed_kind), ["CI123456789B1"]
    )
    assert reasons == []
    assert (
        fields["license_number"].value == "CI-123456789" and fields["license_type"].value == "B1"
    )  # the barcode's text
    assert fields["license_number"].confidence == 0.99 and fields["license_type"].confidence == 0.99
    assert fields["license_number"].raw == printed_number  # what was printed is still on record


def test_a_real_difference_is_not_hidden_by_the_confusion_tolerance():
    for number in ("CI-123456780", "CI-123456798", "XX-123456789"):
        _, reasons = costa_rica.reconcile_license_barcode(license_fields(number=number), ["CI123456789B1"])
        assert reasons == ["barcode_mismatch:license_number"], number


def test_barcode_never_lowers_confidence():
    original = license_fields()
    original["license_number"] = original["license_number"].model_copy(update={"confidence": 0.999})
    fields, _ = costa_rica.reconcile_license_barcode(original, ["CI000000000B1"])
    assert fields["license_number"].confidence == 0.999


def test_disagreement_asks_for_review_without_overwriting():
    fields, reasons = costa_rica.reconcile_license_barcode(license_fields(kind="B2"), ["CI000000000B1"])
    assert reasons == ["barcode_mismatch:license_type"]
    assert fields["license_type"].value == "B2" and fields["license_type"].confidence == 0.78

    _, reasons = costa_rica.reconcile_license_barcode(
        license_fields(number="CI-111111111"), ["CI000000000B1"]
    )
    assert reasons == ["barcode_mismatch:license_number"]


def test_missing_fields_are_filled_from_the_barcode():
    fields, reasons = costa_rica.reconcile_license_barcode({}, ["CI000000000B1"])
    assert reasons == []
    assert fields["license_number"].value == "CI-000000000" and fields["license_type"].value == "B1"
    assert fields["license_number"].side is None  # it did not come from either printed side


def test_barcode_text_is_normalised_before_comparing():
    fields, reasons = costa_rica.reconcile_license_barcode(license_fields(), [" ci-000000000 b1 "])
    assert reasons == [] and fields["license_type"].confidence == 0.99


@pytest.mark.parametrize(
    "barcodes", [[], ["https://example.com"], ["12345"], ["CI000000000"], ["CI000000000Z9"]]
)
def test_barcodes_of_another_shape_are_ignored(barcodes):
    original = license_fields()
    fields, reasons = costa_rica.reconcile_license_barcode(original, barcodes)
    assert fields == original and reasons == []


def test_the_input_is_not_modified():
    original = license_fields()
    costa_rica.reconcile_license_barcode(original, ["CI000000000B1"])
    assert original["license_type"].confidence == 0.78


def test_only_the_first_recognised_barcode_counts():
    _, reasons = costa_rica.reconcile_license_barcode(
        license_fields(), ["junk", "CI000000000B1", "CI999999999A1"]
    )
    assert reasons == []


# --- MRZ to fields ------------------------------------------------------------------------------


def test_mrz_fields_are_confident_when_the_checks_pass():
    fields = documents.from_mrz(mrz.read(TD3))
    assert {k: v.value for k, v in fields.items()} == {
        "document_number": "L898902C3",
        "surname": "ERIKSSON",
        "given_names": "ANNA MARIA",
        "nationality": "UTO",
        "issuing_country": "UTO",
        "birth_date": "1974-08-12",
        "sex": "F",
        "expiry_date": "2012-04-15",
    }
    assert {f.confidence for f in fields.values()} == {0.99}


def test_mrz_confidence_drops_for_what_a_failed_check_covers():
    broken = mrz.read([TD3[0], TD3[1].replace("7408122", "7408123")])  # the birth date no longer matches
    fields = documents.from_mrz(broken)
    assert (
        fields["birth_date"].confidence == 0.5 and fields["surname"].confidence == 0.5
    )  # the whole MRZ is suspect
    assert fields["document_number"].confidence == 0.99  # its own check digit still holds


def test_mrz_fields_skip_what_is_empty():
    assert "document_number" not in documents.from_mrz(mrz.read(make_td3(number="")))


# --- the registered documents -------------------------------------------------------------------


@pytest.mark.parametrize("doc", ["cedula", "driver_license", "dimex"])
def test_every_required_field_is_one_a_parser_can_produce(doc):
    sample = {
        "cedula": stacked(
            "1 9999 9999", "Nombre: ANA", "1ºApellido: PRUEBA", "F. Nac: 12/01/1990 Vence: 05/03/2030"
        ),
        "driver_license": stacked("CI-123456789", "Vencimiento 01-02-2030", "Tipo: B1"),
        "dimex": stacked("155812345678"),
    }[doc]
    spec = documents.get(doc)
    assert set(spec.required) <= set(spec.parse(sample))
