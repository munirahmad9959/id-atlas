"""The registry of document types: its rules, and how a new country plugs in."""

import sys
import textwrap

import pytest
from factories import line, stacked

from id_atlas import countries, documents
from id_atlas.documents import registry
from id_atlas.schemas import Field


@pytest.fixture
def isolated_registry(monkeypatch):
    """A registry copy that a test can add to without leaking into the others."""
    documents.known_types()  # make sure the real documents are loaded first
    monkeypatch.setattr(registry, "_specs", dict(registry._specs))


def spec(**overrides) -> documents.DocumentSpec:
    values = {
        "type": "testland_id",
        "country": "TST",
        "name": "Testland ID",
        "parse": lambda lines: {"id_number": Field(value="1", confidence=1.0)},
        "required": ("id_number",),
    }
    return documents.DocumentSpec(**{**values, **overrides})


def test_the_costa_rican_and_mrz_documents_are_registered():
    assert {"cedula", "driver_license", "dimex", "passport", "id_mrz"} <= set(documents.known_types())


def test_every_spec_is_consistent():
    types = [s.type for s in documents.specs()]
    assert len(types) == len(set(types)) and "unknown" not in types
    for s in documents.specs():
        assert s.required, s.type
        assert s.mrz_based == (s.parse is None), s.type
        if not s.mrz_based:
            assert s.markers, f"{s.type} cannot be recognised without markers"


def test_markers_are_squashed_so_they_can_be_written_naturally():
    s = spec(front_markers=("Cédula de Identidad",), any_markers=("N.° 1",))
    assert s.front_markers == ("CEDULADEIDENTIDAD",) and s.any_markers == ("N1",)


def test_registering_a_type_twice_is_an_error(isolated_registry):
    registry.register(spec())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(spec())


def test_a_registered_document_is_classified_and_reported_on_a_side(isolated_registry):
    registry.register(spec(front_markers=("Testland Identity Card",), back_markers=("Testland Address",)))
    assert documents.classify(stacked("TESTLAND IDENTITY CARD"), None) == "testland_id"
    assert documents.side_guess(stacked("Testland Identity Card")) == "front"
    assert documents.side_guess(stacked("Testland Address")) == "back"


def test_the_document_with_most_markers_wins_and_a_tie_goes_to_the_first(isolated_registry):
    registry.register(spec(type="a", any_markers=("ALPHA", "SHARED")))
    registry.register(spec(type="b", any_markers=("BETA", "SHARED", "EXTRA")))
    assert documents.classify(stacked("SHARED", "EXTRA"), None) == "b"
    assert documents.classify(stacked("SHARED"), None) == "a"


def test_a_country_module_dropped_into_the_package_is_found_on_its_own(tmp_path, monkeypatch):
    documents.known_types()
    monkeypatch.setattr(registry, "_specs", dict(registry._specs))
    monkeypatch.setattr(registry, "_loaded", False)
    monkeypatch.setattr(countries, "__path__", [*countries.__path__, str(tmp_path)])
    monkeypatch.delitem(sys.modules, "id_atlas.countries.fakeland", raising=False)
    (tmp_path / "fakeland.py").write_text(
        textwrap.dedent(
            """
            from id_atlas.documents import DocumentSpec, register

            register(DocumentSpec(type="fakeland_id", country="FKL", name="Fakeland ID", parse=lambda lines: {},
                                  required=("id_number",), any_markers=("Republic of Fakeland",)))
            """
        )
    )
    assert "fakeland_id" in documents.known_types()
    assert documents.classify([line("REPUBLIC OF FAKELAND")], None) == "fakeland_id"
    sys.modules.pop("id_atlas.countries.fakeland", None)
