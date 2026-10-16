from typing import Literal

from pydantic import BaseModel

DocumentType = Literal["cedula", "passport", "driver_license", "dimex", "id_mrz", "unknown"]
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
    format: Literal["TD1", "TD3"]
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


class ExtractionResult(BaseModel):
    document_type: DocumentType
    fields: dict[str, Field]
    mrz: Mrz | None = None
    barcodes: list[str] = []
    sides: list[SideResult] = []
    needs_review: bool
    review_reasons: list[str]
    elapsed_ms: int
