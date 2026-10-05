from __future__ import annotations

import runpy
from unittest.mock import Mock

import pytest
import uvicorn


@pytest.mark.parametrize("profile,port", [("dev", 8070), ("prod", 8080)])
def test_module_startup_uses_installed_namespace(
    monkeypatch: pytest.MonkeyPatch, profile: str, port: int,
) -> None:
    monkeypatch.setenv("PROFILE", profile)
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    run = Mock()
    monkeypatch.setattr(uvicorn, "run", run)

    runpy.run_module("banking_account.main", run_name="__main__")

    run.assert_called_once_with(
        "banking_account.main:app", host="0.0.0.0", port=port,
        proxy_headers=True, forwarded_allow_ips="*",
    )
