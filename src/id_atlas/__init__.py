"""id-atlas: lightweight, self-hosted OCR for identity documents."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("id-atlas")
except PackageNotFoundError:  # run from a source folder without installing the package
    __version__ = "0.0.0+unknown"
