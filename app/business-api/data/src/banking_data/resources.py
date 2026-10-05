"""Explicit resource location for installed data commands."""
import os
from pathlib import Path


def data_directory() -> Path:
    return Path(os.environ.get("DATA_PROJECT_DIR", ".")).expanduser().resolve()
