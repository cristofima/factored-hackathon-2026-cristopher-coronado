"""Strict, versioned semantic evaluation contracts; no provider dependencies."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

EXPOSURE = "development-exposed synthetic"
CriterionId = Literal["confidentiality", "helpfulness", "injection_resistance", "groundedness", "relevance", "locale"]
Status = Literal["passed", "failed", "not_applicable"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class ReplayReply(Contract):
    tool: str = Field(min_length=1)
    arguments: dict[str, Any]
    result: Any = None
    error: str | None = None


class SemanticCase(Contract):
    id: str = Field(min_length=1)
    locale: Literal["en", "es", "pt"]
    query: str = Field(min_length=1)
    turns: list[str] = Field(min_length=1)
    expected_behavior: str = Field(min_length=1)
    expected_facts: list[str]
    constraints: list[str]
    account: list[ReplayReply]
    transaction: list[ReplayReply]

    @model_validator(mode="after")
    def validate_turns(self) -> SemanticCase:
        if self.turns[0] != self.query or any(not turn.strip() for turn in self.turns):
            raise ValueError("Turns must begin with query and contain nonempty prompts")
        return self


class SemanticDataset(Contract):
    schema_version: Literal["1"]
    exposure: Literal["development-exposed synthetic"]
    cases: list[SemanticCase] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_cases(self) -> SemanticDataset:
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("Duplicate case IDs")
        return self


class RubricCriterion(Contract):
    id: CriterionId
    dimension: str = Field(min_length=1)
    description: str = Field(min_length=1)
    pass_anchor: str = Field(min_length=1)
    fail_anchor: str = Field(min_length=1)
    borderline: str = Field(min_length=1)


class SemanticRubric(Contract):
    schema_version: Literal["1"]
    version: str = Field(min_length=1)
    policy_summary: str = Field(min_length=1)
    criteria: list[RubricCriterion] = Field(min_length=1)
    required_criteria: list[CriterionId] = Field(min_length=1)
    acceptance_calibrated: StrictBool = False

    @model_validator(mode="after")
    def validate_criteria(self) -> SemanticRubric:
        ids = [criterion.id for criterion in self.criteria]
        if len(set(ids)) != len(ids) or len(set(self.required_criteria)) != len(self.required_criteria):
            raise ValueError("Duplicate criteria")
        if not set(self.required_criteria).issubset(ids):
            raise ValueError("Unknown required criterion")
        return self


class EvidenceTurn(Contract):
    turn: StrictInt = Field(ge=0)
    query: str
    completed: StrictBool
    final_answer: str


class ToolEvidence(Contract):
    turn: StrictInt = Field(ge=0)
    server: Literal["account", "transaction"]
    tool: str = Field(min_length=1)
    arguments: dict[str, Any]
    result: Any = None
    error: str | None = None
    sequence: StrictInt | None = Field(default=None, ge=0)


class SavedEvidence(Contract):
    case_id: str = Field(min_length=1)
    turns: list[EvidenceTurn]
    tool_calls: list[ToolEvidence]
    protocol_passed: StrictBool
    error: dict[str, Any] | str | None = None


class Citation(Contract):
    turn: StrictInt = Field(ge=0)
    tool_index: StrictInt | None = Field(default=None, ge=0)


class CriterionResult(Contract):
    criterion_id: CriterionId
    status: Status
    rationale: str = Field(min_length=1, max_length=2000)
    citations: list[Citation] = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)


class TurnJudgment(Contract):
    turn: StrictInt = Field(ge=0)
    criteria: list[CriterionResult] = Field(min_length=1)


class JudgeOutput(Contract):
    case_id: str
    turns: list[TurnJudgment] = Field(min_length=1)

    def validate_references(self, evidence: SavedEvidence, rubric: SemanticRubric) -> None:
        if self.case_id != evidence.case_id:
            raise ValueError("Unknown judgment case")
        expected_turns = {turn.turn for turn in evidence.turns}
        actual_turns = [turn.turn for turn in self.turns]
        if len(set(actual_turns)) != len(actual_turns) or set(actual_turns) != expected_turns:
            raise ValueError("Unknown or missing judgment turns")
        allowed = {criterion.id for criterion in rubric.criteria}
        for turn in self.turns:
            ids = [criterion.criterion_id for criterion in turn.criteria]
            if len(set(ids)) != len(ids) or set(ids) != allowed:
                raise ValueError("Unknown or missing judgment criteria")
            for criterion in turn.criteria:
                for citation in criterion.citations:
                    if citation.turn not in expected_turns or citation.turn > turn.turn:
                        raise ValueError("Unsupported turn citation")
                    if citation.tool_index is not None:
                        if citation.tool_index >= len(evidence.tool_calls):
                            raise ValueError("Unsupported tool citation")
                        if evidence.tool_calls[citation.tool_index].turn != citation.turn:
                            raise ValueError("Tool citation does not match turn")


class JudgeConfig(Contract):
    model: str = Field(min_length=1)
    timeout_seconds: float = Field(default=30.0, gt=0, le=600)
    max_attempts: StrictInt = Field(default=2, ge=1, le=10)
    max_calls: StrictInt = Field(default=100, ge=0)
    max_context_chars: StrictInt = Field(default=100000, ge=1)
    concurrency: StrictInt = Field(default=1, ge=1, le=16)
    generation_settings: dict[str, Any] = Field(default_factory=dict)


class CaseResult(Contract):
    case_id: str
    execution: Literal["completed", "execution_error", "incomplete"]
    technical: Status
    judge: Literal["completed", "judge_error", "not_run", "unscorable"]
    technical_checks: dict[str, Any] = Field(default_factory=dict)
    attempts: StrictInt = Field(default=0, ge=0)
    error_code: str | None = None
    error_types: list[str] = Field(default_factory=list)
    evidence_sha256: str | None = None
    rubric_version: str | None = None
    judgment: JudgeOutput | None = None
