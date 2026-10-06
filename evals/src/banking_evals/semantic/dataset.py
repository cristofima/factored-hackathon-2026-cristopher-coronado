"""Load approved checkout resources and reject sensitive evaluation context."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

from banking_evals.resources import repository_root
from banking_evals.semantic.contracts import SemanticDataset, SemanticRubric

_SENSITIVE_KEY = re.compile(r"authorization|password|secret|credential|api[_-]?key|access[_-]?token|refresh[_-]?token|connection[_-]?string", re.I)
_SENSITIVE_VALUE = re.compile(
    r"bearer\s+\S+|\beyJ[\w-]+\.[\w-]+\.[\w-]+\b|"
    r"v1\.[\w-]+\.[a-f0-9]{64}|(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?):\/\/|"
    r"\b(?:password|secret|api[_-]?key|access[_-]?token)\s*[=:]\s*\S+|"
    r"\bsk-[A-Za-z0-9_-]{16,}", re.I,
)
_RAW_KEYS = {"stream_updates", "response", "raw_response", "source_instructions", "system_prompt"}


def ensure_safe(value: Any) -> None:
    """Reject rather than silently redact; explicit synthetic canaries remain data."""
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("Non-string evidence key")
            if _SENSITIVE_KEY.search(key) or key.lower() in _RAW_KEYS:
                raise ValueError("Sensitive or raw evidence field")
            ensure_safe(item)
    elif isinstance(value, list):
        for item in value:
            ensure_safe(item)
    elif isinstance(value, str):
        if _SENSITIVE_VALUE.search(value):
            raise ValueError("Sensitive evidence text")
        for email in re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", value):
            if not email.endswith(".invalid"):
                raise ValueError("Non-synthetic email evidence")
    elif value is not None and type(value) not in {bool, int, float}:
        raise ValueError("Non-JSON evidence value")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Non-finite evidence number")


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def fingerprint(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_dataset(path: str | Path | None = None) -> SemanticDataset:
    source = Path(path) if path is not None else repository_root() / "evals" / "semantic_cases.json"
    dataset = SemanticDataset.model_validate_json(source.read_bytes())
    ensure_safe(dataset.model_dump(mode="json"))
    return dataset


def load_rubric(path: str | Path | None = None) -> SemanticRubric:
    source = Path(path) if path is not None else repository_root() / "evals" / "semantic_rubric.json"
    rubric = SemanticRubric.model_validate_json(source.read_bytes())
    ensure_safe(rubric.model_dump(mode="json"))
    return rubric
