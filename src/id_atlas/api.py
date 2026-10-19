"""HTTP API: upload the images of one identity document, get its fields back."""

import hmac
from contextlib import asynccontextmanager
from importlib.metadata import version
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile

from . import documents, engine, pipeline
from .config import Settings, get_settings
from .documents import UnknownDocumentType
from .imaging import InvalidImage
from .schemas import DocumentInfo, DocumentType, ExtractionResult


@asynccontextmanager
async def lifespan(_: FastAPI):
    engine.warm_up()
    yield


app = FastAPI(
    title="id-atlas",
    version=version("id-atlas"),
    description="Lightweight, self-hosted OCR for identity documents. Results are hints for a human reviewer.",
    lifespan=lifespan,
)

_ERRORS = {
    401: {"description": "Missing or wrong X-API-Key (only when an API key is configured)"},
    413: {"description": "An image is larger than the upload limit"},
    422: {"description": "An image cannot be read, or a required field is missing"},
}


def require_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    if settings.api_key and not hmac.compare_digest(x_api_key or "", settings.api_key):
        raise HTTPException(401, "invalid api key")


def _read_upload(upload: UploadFile, settings: Settings) -> bytes:
    data = upload.file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, "image too large")
    return data


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get(
    "/v1/documents",
    response_model=list[DocumentInfo],
    dependencies=[Depends(require_key)],
    responses={401: _ERRORS[401]},
)
def list_documents() -> list[DocumentInfo]:
    """The document types this service can read. Any of their `type` values can be sent as `document_type`."""
    return [
        DocumentInfo(
            type=spec.type,
            country=spec.country or None,
            name=spec.name,
            two_sided=spec.two_sided,
            verified=spec.verified,
            required=list(spec.required),
        )
        for spec in documents.specs()
    ]


@app.post(
    "/v1/extract/document",
    response_model=ExtractionResult,
    dependencies=[Depends(require_key)],
    responses=_ERRORS,
)
def extract_document(
    settings: Annotated[Settings, Depends(get_settings)],
    front: Annotated[UploadFile, File()],
    back: Annotated[UploadFile | None, File()] = None,
    document_type: Annotated[DocumentType | None, Form()] = None,
) -> ExtractionResult:
    """One document: its front and, when it has one, its back, returned as a single combined result."""
    front_data = _read_upload(front, settings)
    back_data = _read_upload(back, settings) if back is not None else None
    try:
        return pipeline.extract_document(front_data, back_data, settings, document_type)
    except (InvalidImage, UnknownDocumentType) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post(
    "/v1/extract",
    response_model=ExtractionResult,
    dependencies=[Depends(require_key)],
    responses=_ERRORS,
)
def extract(
    settings: Annotated[Settings, Depends(get_settings)],
    file: Annotated[UploadFile, File()],
    document_type: Annotated[DocumentType | None, Form()] = None,
) -> ExtractionResult:
    """One image, read on its own (no front/back checks)."""
    try:
        return pipeline.extract(_read_upload(file, settings), settings, document_type)
    except (InvalidImage, UnknownDocumentType) as exc:
        raise HTTPException(422, str(exc)) from exc
