import os

import pytest
import uvicorn

from id_atlas import cli
from id_atlas.config import Settings, get_settings


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch, tmp_path):
    """No ID_ATLAS_* variable or .env file from the machine running the tests may leak in."""
    for name in [n for n in os.environ if n.startswith(("ID_ATLAS_", "OCR_"))]:
        monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_defaults_are_safe():
    settings = Settings()
    assert settings.host == "127.0.0.1" and settings.port == 8000  # loopback unless told otherwise
    assert settings.api_key is None
    assert settings.max_upload_bytes == 10 * 1024 * 1024
    assert (settings.max_image_side, settings.barcode_max_side) == (1600, 3000)
    assert (settings.rotation_retry_below, settings.review_below) == (0.8, 0.85)


def test_environment_variables_override_defaults(monkeypatch):
    monkeypatch.setenv("ID_ATLAS_HOST", "0.0.0.0")
    monkeypatch.setenv("ID_ATLAS_PORT", "9100")
    monkeypatch.setenv("ID_ATLAS_API_KEY", "k")
    monkeypatch.setenv("ID_ATLAS_REVIEW_BELOW", "0.9")
    settings = Settings()
    assert (settings.host, settings.port, settings.api_key, settings.review_below) == (
        "0.0.0.0",
        9100,
        "k",
        0.9,
    )


def test_a_dotenv_file_is_read(tmp_path):
    (tmp_path / ".env").write_text("ID_ATLAS_API_KEY=from-file\nID_ATLAS_PORT=9200\nUNRELATED=1\n")
    settings = Settings()
    assert settings.api_key == "from-file" and settings.port == 9200


def test_the_real_environment_beats_the_dotenv_file(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("ID_ATLAS_API_KEY=from-file\n")
    monkeypatch.setenv("ID_ATLAS_API_KEY", "from-env")
    assert Settings().api_key == "from-env"


def test_variables_without_the_id_atlas_prefix_are_not_read(monkeypatch):
    monkeypatch.setenv("API_KEY", "unprefixed")
    monkeypatch.setenv("OCR_API_KEY", "other-prefix")
    assert Settings().api_key is None


def test_an_invalid_value_fails_loudly(monkeypatch):
    monkeypatch.setenv("ID_ATLAS_PORT", "not-a-port")
    with pytest.raises(ValueError):
        Settings()


def test_get_settings_is_cached(monkeypatch):
    first = get_settings()
    monkeypatch.setenv("ID_ATLAS_PORT", "9300")
    assert get_settings() is first and first.port == 8000


def test_the_command_serves_the_app_on_the_configured_address(monkeypatch):
    monkeypatch.setenv("ID_ATLAS_HOST", "0.0.0.0")
    monkeypatch.setenv("ID_ATLAS_PORT", "9400")
    served = []
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: served.append((args, kwargs)))
    cli.main()
    assert served == [(("id_atlas.api:app",), {"host": "0.0.0.0", "port": 9400})]
