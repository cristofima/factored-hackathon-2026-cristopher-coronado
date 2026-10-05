"""Bounded logging configuration fallback regressions."""

from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from app.config.logging import load_logging_config


@pytest.mark.parametrize("content", ["", "[]", "null", "version: [", "version: 2"])
def test_invalid_logging_yaml_uses_bounded_fallback(content: str) -> None:
    with patch.object(Path, "exists", return_value=True), patch("builtins.open", return_value=StringIO(content)):
        config = load_logging_config(Path("synthetic-logging.yaml"))
    assert config["version"] == 1
    assert config["root"]["handlers"] == ["console"]


def test_missing_logging_file_uses_bounded_fallback() -> None:
    with patch.object(Path, "exists", return_value=False):
        config = load_logging_config(Path("synthetic-missing.yaml"))
    assert config["version"] == 1
