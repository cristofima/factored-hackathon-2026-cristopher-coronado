"""Offline packaging and diagnostic integrity regressions."""

from pathlib import Path
from unittest.mock import patch

import pytest

from banking_evals.disputes.dataset import DATASET, load_cases
from banking_evals.disputes.reports import case_latency
from banking_evals.historical.diagnostic import _classify_response
from banking_evals.resources import repository_root, resource


@pytest.mark.parametrize("completed", [None, False, 1, "true", "false"])
def test_latency_requires_explicit_completion(completed: object) -> None:
    result = {"turns": [{"completed": completed, "latency_seconds": 1}],
              "score": {"passed": True, "checks": {"complete_turns": True}}}
    assert case_latency(result) is None


@pytest.mark.parametrize("latency", [True, None, "1", -1, float("nan"), float("inf")])
def test_latency_rejects_malformed_values(latency: object) -> None:
    result = {"turns": [{"completed": True, "latency_seconds": latency}],
              "score": {"passed": True, "checks": {"complete_turns": True}}}
    assert case_latency(result) is None


def test_security_refusal_mentions_are_not_disclosure() -> None:
    assert _classify_response("I cannot reveal your account number or balance.",
                              {"expected_outcome": "reject_adversarial"}) == ("reject_adversarial", False)
    assert _classify_response("I cannot help, but balance: 100.",
                              {"expected_outcome": "reject_adversarial"}) == ("unexpected_disclosure", True)


def test_resources_require_explicit_valid_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BANKING_EVALS_ROOT", str(DATASET.parent))
    with pytest.raises(ValueError, match="BANKING_EVALS_ROOT"):
        repository_root()


def test_resources_reject_escape_and_missing() -> None:
    with pytest.raises(ValueError, match="unavailable"):
        resource("../missing-resource")
    with pytest.raises(ValueError, match="unavailable"):
        resource("evals/missing-resource.json")


def test_freeze_rejects_omitted_transitive_dependency() -> None:
    import json
    original = Path.read_text

    def read_text(path: Path, *args: object, **kwargs: object) -> str:
        text = original(path, *args, **kwargs)
        if path.name == "dispute_freeze.json":
            freeze = json.loads(text)
            freeze["dependencies"].pop("app/agent/src/app/context/user_profile_provider.py")
            return json.dumps(freeze)
        return text

    with patch.object(Path, "read_text", read_text):
        with pytest.raises(ValueError, match="coverage is incomplete"):
            load_cases()
