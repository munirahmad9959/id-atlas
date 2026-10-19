import pytest
from factories import (
    cedula_back,
    cedula_front,
    encode,
    license_back,
    license_front,
    make_td3,
    passport_page,
)
from fastapi.testclient import TestClient

from id_atlas import documents
from id_atlas.api import app
from id_atlas.config import Settings, get_settings
from id_atlas.schemas import ExtractionResult

FRONT, BACK = encode(license_front()), encode(license_back())
PASSPORT = encode(passport_page(make_td3()))


def png(name: str, data: bytes):
    return (name, data, "image/png")


@pytest.fixture
def client():
    app.dependency_overrides.clear()
    with TestClient(app) as test_client:  # entering the context runs the lifespan, which loads the models
        yield test_client
    app.dependency_overrides.clear()


def configure(**overrides):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, **overrides)


# --- the service itself -------------------------------------------------------------------------


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_the_documented_routes(client):
    spec = client.get("/openapi.json").json()
    assert set(spec["paths"]) == {"/health", "/v1/documents", "/v1/extract", "/v1/extract/document"}
    assert spec["info"]["title"] == "id-atlas" and spec["info"]["version"]
    document = spec["paths"]["/v1/extract/document"]["post"]
    assert {"401", "413", "422"} <= set(document["responses"])


# --- the supported documents -------------------------------------------------------------------


def test_the_supported_documents_are_listed(client):
    response = client.get("/v1/documents")
    assert response.status_code == 200
    by_type = {d["type"]: d for d in response.json()}
    assert set(by_type) == set(documents.known_types())
    assert by_type["cedula"] == {
        "type": "cedula",
        "country": "CRI",
        "name": "Costa Rican cédula de identidad",
        "two_sided": True,
        "verified": True,
        "required": ["document_number", "given_names", "surname", "birth_date", "expiry_date"],
    }
    assert by_type["passport"]["country"] is None and by_type["passport"]["two_sided"] is False
    assert all(d["type"] != "unknown" for d in by_type.values())


def test_every_listed_type_can_be_sent_as_a_hint(client):
    for item in client.get("/v1/documents").json():
        files = {"front": png("f.png", FRONT)}
        response = client.post("/v1/extract/document", files=files, data={"document_type": item["type"]})
        assert response.status_code == 200 and response.json()["document_type"] == item["type"]


def test_the_listing_requires_the_key_when_one_is_set(client):
    configure(api_key="s3cret")
    assert client.get("/v1/documents").status_code == 401
    assert client.get("/v1/documents", headers={"X-API-Key": "s3cret"}).status_code == 200


# --- reading a document -------------------------------------------------------------------------


def test_front_and_back_return_one_combined_result(client):
    response = client.post(
        "/v1/extract/document", files={"front": png("f.png", FRONT), "back": png("b.png", BACK)}
    )
    assert response.status_code == 200
    result = ExtractionResult.model_validate(response.json())  # the body honours the published schema
    assert result.document_type == "driver_license" and [s.side for s in result.sides] == ["front", "back"]
    assert result.barcodes == ["CI123456789B1"] and "missing_back_side" not in result.review_reasons


def test_the_back_is_optional_and_its_absence_is_flagged(client):
    response = client.post("/v1/extract/document", files={"front": png("f.png", FRONT)})
    assert response.status_code == 200 and "missing_back_side" in response.json()["review_reasons"]


def test_a_document_type_can_be_forced(client):
    files = {"front": png("f.png", encode(cedula_front()))}
    assert client.post("/v1/extract/document", files=files).json()["document_type"] == "cedula"
    forced = client.post("/v1/extract/document", files=files, data={"document_type": "dimex"})
    assert forced.json()["document_type"] == "dimex"


def test_an_unknown_document_type_is_rejected(client):
    response = client.post(
        "/v1/extract/document", files={"front": png("f.png", FRONT)}, data={"document_type": "visa"}
    )
    assert response.status_code == 422


def test_the_single_image_endpoint(client):
    response = client.post("/v1/extract", files={"file": png("p.png", PASSPORT)})
    body = response.json()
    assert response.status_code == 200 and body["document_type"] == "passport" and body["mrz"]["valid"]
    assert body["sides"][0]["side"] == "front" and len(body["sides"]) == 1


def test_the_single_image_endpoint_never_flags_a_missing_back(client):
    response = client.post("/v1/extract", files={"file": png("f.png", encode(cedula_front()))})
    assert "missing_back_side" not in response.json()["review_reasons"]


# --- bad input ----------------------------------------------------------------------------------


def test_an_unreadable_side_is_named(client):
    files = {"front": png("f.png", FRONT), "back": png("b.png", b"junk")}
    response = client.post("/v1/extract/document", files=files)
    assert response.status_code == 422 and response.json()["detail"] == "back: not a readable image"
    files = {"front": png("f.png", b"junk")}
    assert client.post("/v1/extract/document", files=files).json()["detail"] == "front: not a readable image"


def test_missing_parts_are_rejected(client):
    assert client.post("/v1/extract/document").status_code == 422
    assert client.post("/v1/extract").status_code == 422
    assert client.post("/v1/extract/document", files={"back": png("b.png", BACK)}).status_code == 422


def test_an_unreadable_single_image(client):
    assert client.post("/v1/extract", files={"file": png("x.png", b"junk")}).status_code == 422


@pytest.mark.parametrize(
    "path, files",
    [
        ("/v1/extract/document", {"front": png("f.png", FRONT)}),
        ("/v1/extract", {"file": png("f.png", FRONT)}),
    ],
)
def test_oversized_uploads_are_refused(client, path, files):
    configure(max_upload_bytes=1000)
    assert client.post(path, files=files).status_code == 413


def test_the_back_is_size_checked_too(client):
    configure(max_upload_bytes=len(FRONT) + 10)  # the front fits, the back does not
    files = {"front": png("f.png", FRONT), "back": png("b.png", encode(cedula_back()))}
    assert client.post("/v1/extract/document", files=files).status_code == 413


# --- the API key --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path, files",
    [
        ("/v1/extract/document", {"front": png("f.png", FRONT)}),
        ("/v1/extract", {"file": png("f.png", FRONT)}),
    ],
)
def test_every_extraction_route_requires_the_key_when_one_is_set(client, path, files):
    configure(api_key="s3cret")
    assert client.post(path, files=files).status_code == 401
    assert client.post(path, files=files, headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.post(path, files=files, headers={"X-API-Key": ""}).status_code == 401
    assert client.post(path, files=files, headers={"X-API-Key": "s3cret"}).status_code == 200


def test_no_key_is_needed_when_none_is_configured(client):
    assert client.post("/v1/extract/document", files={"front": png("f.png", FRONT)}).status_code == 200


def test_health_stays_open_for_orchestrators(client):
    configure(api_key="s3cret")
    assert client.get("/health").status_code == 200
