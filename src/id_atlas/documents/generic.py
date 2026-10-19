"""Documents that are read from their machine-readable zone: passports and other ICAO 9303 documents.

They belong to no country module, because the MRZ format is the same everywhere.
"""

from ..schemas import Field, Mrz
from .registry import DocumentSpec, register
from .text import present

_MRZ_REQUIRED = ("document_number", "surname", "given_names", "birth_date", "expiry_date")

# The word "passport" in the main languages of travel documents: marks a passport page when no MRZ could
# be read. Add a language here when a document needs it.
PASSPORT_WORDS = ("PASSPORT", "PASAPORTE", "PASSEPORT", "PASSAPORTO", "REISEPASS")

register(
    DocumentSpec(
        type="passport",
        country="",
        name="Passport",
        parse=None,
        required=_MRZ_REQUIRED,
        verified=True,
        mrz_based=True,
    )
)
register(
    DocumentSpec(
        type="id_mrz",
        country="",
        name="Identity document with a machine-readable zone",
        parse=None,
        required=_MRZ_REQUIRED,
        verified=True,
        mrz_based=True,
    )
)


def from_mrz(mrz: Mrz) -> dict[str, Field]:
    """Fields of a passport or other MRZ document; confidence reflects whether its check digits passed."""

    def field(value: str | None, ok: bool) -> Field | None:
        return Field(value=value or None, raw=value, confidence=0.99 if ok else 0.5) if value else None

    c = mrz.checks
    return present(
        document_number=field(mrz.document_number, c["document_number"]),
        surname=field(mrz.surname, mrz.valid),
        given_names=field(mrz.given_names, mrz.valid),
        nationality=field(mrz.nationality, mrz.valid),
        issuing_country=field(mrz.issuing_country, mrz.valid),
        birth_date=field(mrz.birth_date, c["birth_date"]),
        sex=field(mrz.sex, mrz.valid),
        expiry_date=field(mrz.expiry_date, c["expiry_date"]),
    )
