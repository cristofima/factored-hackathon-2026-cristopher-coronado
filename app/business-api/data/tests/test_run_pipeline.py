from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from banking_data.ingestion.run_pipeline import (
    PipelineSettings,
    PipelineStep,
    build_artifacts,
    build_steps,
    run_pipeline,
)
from banking_data.shared import parse_customer_ids


def test_settingsRequireSourceDirectory() -> None:
    with pytest.raises(ValueError, match="DATA_SOURCE_DIR"):
        PipelineSettings.from_environment({})


def test_buildArtifactsUsesSingleDateSuffixForOneDay(tmp_path: Path) -> None:
    settings = PipelineSettings(tmp_path, tmp_path / "artifacts", tmp_path / "manifests")

    artifacts = build_artifacts(settings, date(2026, 3, 1), date(2026, 3, 1))

    assert artifacts.profile.name == "eda_profile_2026-03-01.json"
    assert artifacts.scope.name == "scope_manifest_2026-03-01.json"
    assert artifacts.manifest.name == "load_manifest_2026-03-01.json"


def test_buildArtifactsUsesBothDatesForRange(tmp_path: Path) -> None:
    settings = PipelineSettings(tmp_path, tmp_path / "artifacts", tmp_path / "manifests")

    artifacts = build_artifacts(settings, date(2026, 3, 1), date(2026, 5, 31))

    assert artifacts.manifest.name == "load_manifest_2026-03-01_2026-05-31.json"


def test_parseCustomerIdsTrimsAndRemovesDuplicates() -> None:
    customer_ids = parse_customer_ids(" C001, C002,C001 ,C003 ")

    assert customer_ids == ("C001", "C002", "C003")


def test_parseCustomerIdsRejectsEmptyValue() -> None:
    with pytest.raises(ValueError, match="at least one"):
        parse_customer_ids(" , , ")


def test_buildArtifactsUsesStableCustomerSuffix(tmp_path: Path) -> None:
    settings = PipelineSettings(tmp_path, tmp_path / "artifacts", tmp_path / "manifests")

    artifacts = build_artifacts(
        settings,
        date(2026, 3, 1),
        date(2026, 3, 1),
        ("C002", "C001"),
    )
    reversed_artifacts = build_artifacts(
        settings,
        date(2026, 3, 1),
        date(2026, 3, 1),
        ("C001", "C002"),
    )

    assert artifacts.manifest.name.startswith("load_manifest_2026-03-01_customers-2-")
    assert artifacts.manifest.name == reversed_artifacts.manifest.name


def test_buildStepsPassesCustomerIdsToEdaAndLoad(tmp_path: Path) -> None:
    settings = PipelineSettings(tmp_path, tmp_path / "artifacts", tmp_path / "manifests")
    artifacts = build_artifacts(
        settings,
        date(2026, 3, 1),
        date(2026, 3, 1),
        ("C001", "C002"),
    )

    steps = build_steps(
        settings,
        artifacts,
        date(2026, 3, 1),
        date(2026, 3, 1),
        50,
        ("C001", "C002"),
    )

    eda_command = steps[0].command
    load_command = steps[2].command
    assert eda_command[eda_command.index("--customer-ids") + 1] == "C001,C002"
    assert load_command[load_command.index("--customer-ids") + 1] == "C001,C002"
    assert "--customer-ids" not in steps[1].command
    assert "--customer-ids" not in steps[3].command


def test_runPipelineExecutesStepsInOrder(tmp_path: Path) -> None:
    settings = PipelineSettings(tmp_path, tmp_path / "artifacts", tmp_path / "manifests")
    executed: list[str] = []

    def execute(step: PipelineStep) -> None:
        executed.append(step.name)
        if step.name == "scope selection":
            artifacts = build_artifacts(settings, date(2026, 3, 1), date(2026, 3, 1))
            artifacts.scope.write_text(json.dumps({"approved": True}), encoding="utf-8")

    run_pipeline(
        settings,
        date(2026, 3, 1),
        date(2026, 3, 1),
        50,
        execute_step=execute,
    )

    assert executed == [
        "EDA profile",
        "scope selection",
        "scoped load",
        "load verification",
    ]


def test_runPipelineStopsWhenScopeIsRejected(tmp_path: Path) -> None:
    settings = PipelineSettings(tmp_path, tmp_path / "artifacts", tmp_path / "manifests")
    executed: list[str] = []

    def execute(step: PipelineStep) -> None:
        executed.append(step.name)
        if step.name == "scope selection":
            artifacts = build_artifacts(settings, date(2026, 3, 1), date(2026, 3, 1))
            artifacts.scope.write_text(json.dumps({"approved": False}), encoding="utf-8")

    with pytest.raises(RuntimeError, match="not approved"):
        run_pipeline(
            settings,
            date(2026, 3, 1),
            date(2026, 3, 1),
            50,
            execute_step=execute,
        )

    assert executed == ["EDA profile", "scope selection"]
