from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest

from banking_data.resources import data_directory


@pytest.mark.parametrize(
    ("entrypoint", "implementation"),
    [
        ("run_pipeline", "ingestion.run_pipeline"),
        ("load_scoped_data", "ingestion.load_scoped_data"),
        ("verify_load", "ingestion.verify_load"),
        ("build_monthly_snapshots", "snapshots.build_monthly_snapshots"),
        ("verify_monthly_snapshots", "snapshots.verify_monthly_snapshots"),
        ("eda_profile", "analysis.eda_profile"),
        ("eda_select_scope", "analysis.eda_select_scope"),
        ("inspect_sources", "analysis.inspect_sources"),
        ("profile_transaction_semantics", "analysis.profile_transaction_semantics"),
        ("evaluate_fraud_threshold", "analysis.evaluate_fraud_threshold"),
    ],
)
def test_compatibleCliUsesNestedImplementation(entrypoint: str, implementation: str) -> None:
    adapter = import_module(f"banking_data.{entrypoint}")
    canonical = import_module(f"banking_data.{implementation}")

    assert adapter.main is canonical.main


def test_resourceDirectoryUsesExplicitProjectNotPackageDepth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_PROJECT_DIR", str(tmp_path))

    assert data_directory() == tmp_path.resolve()
