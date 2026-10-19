"""The registry of document types: what each one looks like and how to read it.

A document type is described by one `DocumentSpec`. Country modules in `id_atlas.countries` register their
specs when they are imported, and every module in that package is imported automatically the first time the
registry is used, so supporting another country means adding one module there and editing nothing else.
"""

import importlib
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass

from ..engine import Line
from ..schemas import Field
from .fields import FIELD_NAMES
from .text import squash

Parser = Callable[[list[Line]], dict[str, Field]]
# Cross-checks parsed fields against the document's barcodes: (fields, barcode texts) -> (fields, reasons).
Reconciler = Callable[[dict[str, Field], list[str]], tuple[dict[str, Field], list[str]]]


class UnknownDocumentType(ValueError):
    """A document type that no module has registered."""


@dataclass(frozen=True)
class DocumentSpec:
    """One kind of identity document.

    Markers are words printed on the document. Write them naturally ("Licencia de Conducir"): case, accents,
    spaces and punctuation are ignored when matching, because the OCR often merges or splits words.
    `front_markers` and `back_markers` appear on only one side, so they also tell the sides apart.
    `any_markers` identify the document without saying which side it is.
    """

    type: str  # short snake_case name, unique across countries; it is what the API returns
    country: str  # ISO 3166-1 alpha-3 code of the issuing country, such as "CRI"
    name: str  # for people, such as "Costa Rican driver's license"
    parse: Parser | None  # reads the fields from a side's OCR lines; None for documents read from an MRZ
    required: tuple[str, ...]  # a missing or unreadable field sends the document to manual review
    front_markers: tuple[str, ...] = ()
    back_markers: tuple[str, ...] = ()
    any_markers: tuple[str, ...] = ()
    two_sided: bool = False  # only complete with both sides: a missing back sends it to review
    verified: bool = (
        False  # False until the parser is proven on enough real documents: always asks for review
    )
    reconcile: Reconciler | None = None  # optional cross-check against barcodes
    mrz_based: bool = False  # read from the machine-readable zone instead of by a parser

    def __post_init__(self) -> None:
        if unknown := [name for name in self.required if name not in FIELD_NAMES]:
            raise ValueError(f"{self.type}: required fields not in FIELD_NAMES: {unknown}")
        for name in ("front_markers", "back_markers", "any_markers"):
            object.__setattr__(self, name, tuple(squash(m) for m in getattr(self, name)))

    @property
    def markers(self) -> tuple[str, ...]:
        return self.front_markers + self.back_markers + self.any_markers


_specs: dict[str, DocumentSpec] = {}
_loaded = False


def register(spec: DocumentSpec) -> DocumentSpec:
    if spec.type in _specs:
        raise ValueError(f"document type {spec.type!r} is already registered")
    _specs[spec.type] = spec
    return spec


def _load() -> None:
    """Register the built-in MRZ documents and import every country module once."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    from .. import countries
    from . import generic  # noqa: F401  (registers passport and id_mrz)

    for module in pkgutil.iter_modules(countries.__path__):
        importlib.import_module(f"{countries.__name__}.{module.name}")


def specs() -> list[DocumentSpec]:
    """Every registered spec, in registration order (the order breaks ties when classifying)."""
    _load()
    return list(_specs.values())


def get(document_type: str) -> DocumentSpec | None:
    _load()
    return _specs.get(document_type)


def known_types() -> list[str]:
    return [spec.type for spec in specs()]
