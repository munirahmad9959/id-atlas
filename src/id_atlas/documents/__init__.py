"""Document types and how to read them. See `registry.DocumentSpec` and `id_atlas.countries`."""

from .classify import classify, side_guess
from .generic import from_mrz
from .registry import DocumentSpec, UnknownDocumentType, get, known_types, register, specs

__all__ = [
    "DocumentSpec",
    "UnknownDocumentType",
    "classify",
    "from_mrz",
    "get",
    "known_types",
    "register",
    "side_guess",
    "specs",
]
