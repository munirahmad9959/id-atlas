"""The `id-atlas` command: serve the HTTP API."""

import uvicorn

from .config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run("id_atlas.api:app", host=settings.host, port=settings.port)
