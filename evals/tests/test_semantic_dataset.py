"""Resource loading and synthetic context rejection tests."""

from collections.abc import Iterator
import json
from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from banking_evals.semantic.dataset import canonical_hash, ensure_safe, fingerprint, load_dataset, load_rubric
from banking_evals.semantic.judge import project_evidence
from banking_evals.semantic.contracts import SemanticCase


def case() -> SemanticCase:
    return SemanticCase(id="case", locale="en", query="Balance?", turns=["Balance?"],
        expected_behavior="Answer grounded balance", expected_facts=[], constraints=[], account=[], transaction=[])


@pytest.fixture
def artifact_dir() -> Iterator[Path]:
    path = Path.cwd() / "evals" / f"semantic-test-artifacts-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def test_load_strict_resources(artifact_dir: Path) -> None:
    dataset_path = artifact_dir / "dataset.json"
    dataset_path.write_text(json.dumps(dict(schema_version="1", exposure="development-exposed synthetic",
                                           cases=[case().model_dump()])), encoding="utf-8")
    assert load_dataset(dataset_path).cases[0].id == "case"
    assert len(fingerprint(dataset_path)) == 64
    rubric_path = artifact_dir / "rubric.json"
    rubric_path.write_text(json.dumps(dict(schema_version="1", version="1", policy_summary="Only facts.",
        criteria=[dict(id="locale", dimension="locale", description="Use stored locale",
                       pass_anchor="Correct", fail_anchor="Wrong", borderline="Mixed")],
        required_criteria=["locale"], acceptance_calibrated=False)), encoding="utf-8")
    assert load_rubric(rubric_path).version == "1"
    dataset_path.write_text('{"schema_version":"1","unexpected":true}', encoding="utf-8")
    with pytest.raises(ValidationError):
        load_dataset(dataset_path)


@pytest.mark.parametrize("value", [dict(password="synthetic"), dict(authorization="value"),
    "Bearer fake-sensitive-value", "postgresql://user:pass@host/database", "customer@real.example",
    dict(raw_response={}), float("nan"), "sk-abcdefghijklmnop123456789"])
def test_reject_sensitive_context(value: Any) -> None:
    with pytest.raises(ValueError):
        ensure_safe(value)


def test_synthetic_canary_and_invalid_domain_are_permitted() -> None:
    ensure_safe({"answer": "CANARY_PRIVATE_DATA belongs to synthetic@example.invalid"})
    assert canonical_hash({"b": 2, "a": 1}) == canonical_hash({"a": 1, "b": 2})


def test_runner_projection_omits_provider_stream_without_mutating_input() -> None:
    raw = dict(case_id="case", protocol_passed=True, error=None,
        turns=[dict(turn=0, query="Balance?", completed=True, final_answer="Ten.",
                    stream_updates=["Bearer provider-sensitive"], response={"secret": "provider"})],
        tool_calls=[], source_instructions="Never upload me", identity_fixture="provider data")
    saved = project_evidence(raw, case())
    assert "stream_updates" not in saved.turns[0].model_dump()
    assert raw["turns"][0]["response"] == {"secret": "provider"}


@pytest.mark.parametrize("turns", [
    [dict(turn=1, query="Balance?", completed=True, final_answer="Ten")],
    [dict(turn=0, query="Changed query", completed=True, final_answer="Ten")],
    [dict(turn=0, query="Balance?", completed=True, final_answer="Ten")] * 2,
])
def test_projection_rejects_unknown_changed_duplicate_turns(turns: list[dict[str, Any]]) -> None:
    with pytest.raises(ValueError):
        project_evidence(dict(case_id="case", protocol_passed=True, error=None, turns=turns, tool_calls=[]), case())
