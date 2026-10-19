from typing import Literal

from pydantic import BaseModel

# The name of a registered document type (see `documents.known_types()`), or "unknown".
DocumentType = str
Side = Literal["front", "back"]


class Field(BaseModel):
    value: str | None
    raw: str | None = None
    confidence: float
    side: Side | None = None


class SideResult(BaseModel):
    side: Side
    document_type: DocumentType
    fields_found: int


class Mrz(BaseModel):
    format: Literal["TD1", "TD2", "TD3"]
    lines: list[str]
    document_code: str
    issuing_country: str
    surname: str
    given_names: str
    document_number: str
    nationality: str
    birth_date: str | None
    sex: str | None
    expiry_date: str | None
    personal_number: str
    checks: dict[str, bool]
    valid: bool


class DocumentInfo(BaseModel):
    """One document type this service can read."""

    type: DocumentType
    country: str | None  # ISO 3166-1 alpha-3 of the issuing country; null for any country (an MRZ document)
    name: str
    two_sided: bool
    verified: bool
    required: list[str]


class ExtractionResult(BaseModel):
    document_type: DocumentType
    # Issuing country, ISO 3166-1 alpha-3: the document type's own, or the one its MRZ states; null if unknown.
    country: str | None = None
    fields: dict[str, Field]
    mrz: Mrz | None = None
    barcodes: list[str] = []
    sides: list[SideResult] = []
    needs_review: bool
    review_reasons: list[str]
    elapsed_ms: int
