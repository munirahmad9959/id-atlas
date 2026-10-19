"""Costa Rican identity documents: the cédula de identidad, the driver's license and the DIMEX.

The parsers were built from a handful of real cards and specimens, so treat their accuracy as unproven
until tested on a larger set of real photos.
"""

import re

from ..documents import DocumentSpec, register
from ..documents.text import SEP, Reader, Style, fold_confusables, present
from ..engine import Line
from ..schemas import Field

COUNTRY = "CRI"

# Cards are printed in Spanish: its months, the "de" in "5 de marzo de 2030", and the words that label a field.
STYLE = Style(
    label_words=(
        r"NOMBRE|APELLIDO|NACIMIENTO|F\.\s*NAC|VENC|EXPEDICI|DOMICILIO|PADRE|MADRE"
        r"|N[UÚ]MERO\s+DE\s+C[EÉ]DULA"
    ),
    months={
        "ENE": 1,
        "FEB": 2,
        "MAR": 3,
        "ABR": 4,
        "MAY": 5,
        "JUN": 6,
        "JUL": 7,
        "AGO": 8,
        "SEP": 9,
        "SET": 9,
        "OCT": 10,
        "NOV": 11,
        "DIC": 12,
    },
    date_joiners=("DE",),
)

# --- Cédula de identidad ------------------------------------------------------------------------

_NUMBER = re.compile(r"(?<!\d)([1-9])[\s-]?(\d{4})[\s-]?(\d{4})(?!\d)")
_BIRTH = r"(?:F\.|FECHA(?:\s+DE)?)\s*NAC\w*"
_EXPIRY = r"VENC(?:E|IMIENTO)"


def parse_cedula(lines: list[Line]) -> dict[str, Field]:
    # Parents' names, birthplace and electoral address are printed on the card but deliberately not read.
    read = Reader(lines, STYLE)
    fields = present(
        given_names=read.text_after(r"NOMBRE(?!\s*(?:DEL?|DE\s+LA)\b)"),
        surname=read.text_after(r"1\s*[ºo°.]?\s*APELLIDO"),
        second_surname=read.text_after(r"2\s*[ºo°.]?\s*APELLIDO"),
        birth_date=read.date_after(_BIRTH),
        expiry_date=read.date_after(_EXPIRY),
    )
    # The number is printed unlabeled on the front and labeled on the back.
    texts = read.candidates_after(r"N[UÚ]MERO\s+DE\s+C[EÉ]DULA") + [(ln.text, ln) for ln in lines]
    for text, ln in texts:
        if m := _NUMBER.search(text):
            fields["document_number"] = Field(
                value="".join(m.groups()), raw=m.group(0), confidence=round(ln.score, 3)
            )
            break
    return fields


# --- Driver's license ---------------------------------------------------------------------------


def parse_license(lines: list[Line]) -> dict[str, Field]:
    read = Reader(lines, STYLE)
    return present(
        document_number=read.text_match(r"\b([A-Z]{1,3}-?\d{6,12})\b"),
        issue_date=read.date_after(r"EXPEDICI[OÓ]N"),
        birth_date=read.date_after(r"NACIMIENTO"),
        expiry_date=read.date_after(r"VENCIMIENTO"),
        license_category=read.text_match(r"TIPO" + SEP + r"([A-E]\d?)\b"),
    )


_LICENSE_BARCODE = re.compile(r"^([A-Z]{1,3})(\d{6,12})([A-E]\d?)$")


def reconcile_license_barcode(
    fields: dict[str, Field], barcodes: list[str]
) -> tuple[dict[str, Field], list[str]]:
    """Cross-check a license against its PDF417, which carries the number followed by the license type.

    Seen on one real license only, so a barcode of any other shape is ignored. A printed value that
    agrees with the barcode, allowing for letters the OCR confuses (an I read as l), is replaced by the
    machine-read text and made confident; one that truly differs is never overwritten, it only asks
    for review.
    """
    fields = dict(fields)
    reasons = []
    for text in barcodes:
        if not (m := _LICENSE_BARCODE.match(re.sub(r"[\s-]", "", text.upper()))):
            continue
        prefix, digits, license_category = m.groups()
        expected = {"document_number": f"{prefix}-{digits}", "license_category": license_category}
        for name, display in expected.items():
            field = fields.get(name)
            if field is None or not field.value:
                fields[name] = Field(value=display, raw=text, confidence=0.99)
            elif fold_confusables(field.value) == fold_confusables(display):
                fields[name] = field.model_copy(
                    update={"value": display, "confidence": max(field.confidence, 0.99)}
                )
            else:
                reasons.append(f"barcode_mismatch:{name}")
        break
    return fields, reasons


# --- DIMEX (residence card) ---------------------------------------------------------------------


def parse_dimex(lines: list[Line]) -> dict[str, Field]:
    return present(document_number=Reader(lines, STYLE).text_match(r"(?<!\d)(\d{11,12})(?!\d)"))


# --- Registration -------------------------------------------------------------------------------
# The order matters when two documents match equally well: the license is tried before the others.

register(
    DocumentSpec(
        type="driver_license",
        country=COUNTRY,
        name="Costa Rican driver's license",
        parse=parse_license,
        required=("document_number", "expiry_date", "license_category"),
        front_markers=("Licencia de Conducir",),
        back_markers=("Educación Vial", "Clasificación"),
        any_markers=("COSEVI",),
        two_sided=True,
        reconcile=reconcile_license_barcode,
    )
)
register(
    DocumentSpec(
        type="dimex",
        country=COUNTRY,
        name="Costa Rican DIMEX (residence card)",
        parse=parse_dimex,
        required=("document_number",),
        any_markers=("DIMEX", "Documento de Identidad Migratorio"),
        two_sided=True,
    )
)
register(
    DocumentSpec(
        type="cedula",
        country=COUNTRY,
        name="Costa Rican cédula de identidad",
        parse=parse_cedula,
        required=("document_number", "given_names", "surname", "birth_date", "expiry_date"),
        front_markers=("Cédula de Identidad", "Tribunal Supremo"),
        back_markers=("Domicilio Electoral", "Nombre del Padre", "Nombre de la Madre", "Lugar de Nacimiento"),
        two_sided=True,
        verified=True,
    )
)
