from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings, read from ID_ATLAS_* environment variables or a local .env file."""

    model_config = SettingsConfigDict(env_prefix="ID_ATLAS_", env_file=".env", extra="ignore")

    # When set, every /v1 request must send it in the X-API-Key header.
    api_key: str | None = None
    max_upload_bytes: int = 10 * 1024 * 1024
    # Longest image side fed to the OCR engine; larger photos are downscaled.
    max_image_side: int = 1600
    # Barcodes are decoded from a larger copy: downscaling to OCR size can destroy small bars.
    barcode_max_side: int = 3000
    # Below this mean line confidence the image is retried at other rotations.
    rotation_retry_below: float = 0.8
    # Fields under this confidence send the document to manual review.
    review_below: float = 0.85


@lru_cache
def get_settings() -> Settings:
    return Settings()
