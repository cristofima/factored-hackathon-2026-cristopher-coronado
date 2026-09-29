from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(DATA_DIR) not in sys.path:
    sys.path.insert(0, str(DATA_DIR))

from scripts.shared import parse_customer_ids


@dataclass(frozen=True)
class PipelineSettings:
    source_dir: Path
    artifacts_dir: Path
    manifest_dir: Path

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> PipelineSettings:
        source = environment.get("DATA_SOURCE_DIR", "").strip()
        if not source:
            raise ValueError("DATA_SOURCE_DIR must be configured in the data .env file")

        artifacts = environment.get("DATA_ARTIFACTS_DIR", "").strip()
        manifest = environment.get("DATA_MANIFEST_DIR", "").strip()
        return cls(
            source_dir=Path(source).expanduser(),
            artifacts_dir=Path(artifacts).expanduser() if artifacts else DATA_DIR / "artifacts",
            manifest_dir=Path(manifest).expanduser() if manifest else DATA_DIR / "artifacts",
        )


@dataclass(frozen=True)
class PipelineArtifacts:
    profile: Path
    scope: Path
    manifest: Path


@dataclass(frozen=True)
class PipelineStep:
    name: str
    command: tuple[str, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run EDA, scope selection, scoped load, and verification in order."
    )
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--end-date", type=date.fromisoformat, required=True)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument(
        "--customer-ids",
        help="Comma-separated customer IDs to migrate, for example C001,C002,C003.",
    )
    return parser.parse_args()


def build_artifacts(
    settings: PipelineSettings,
    start_date: date,
    end_date: date,
    customer_ids: tuple[str, ...] = (),
) -> PipelineArtifacts:
    suffix = start_date.isoformat()
    if end_date != start_date:
        suffix = f"{suffix}_{end_date.isoformat()}"
    if customer_ids:
        digest = hashlib.sha256(",".join(sorted(customer_ids)).encode("utf-8")).hexdigest()[:8]
        suffix = f"{suffix}_customers-{len(customer_ids)}-{digest}"

    return PipelineArtifacts(
        profile=settings.artifacts_dir / f"eda_profile_{suffix}.json",
        scope=settings.artifacts_dir / f"scope_manifest_{suffix}.json",
        manifest=settings.manifest_dir / f"load_manifest_{suffix}.json",
    )


def build_steps(
    settings: PipelineSettings,
    artifacts: PipelineArtifacts,
    start_date: date,
    end_date: date,
    batch_size: int,
    customer_ids: tuple[str, ...] = (),
) -> tuple[PipelineStep, ...]:
    common_dates = (
        "--start-date",
        start_date.isoformat(),
        "--end-date",
        end_date.isoformat(),
    )
    customer_arguments = (
        ("--customer-ids", ",".join(customer_ids))
        if customer_ids
        else ()
    )
    return (
        PipelineStep(
            "EDA profile",
            (
                sys.executable,
                str(SCRIPTS_DIR / "eda_profile.py"),
                "--source",
                str(settings.source_dir),
                "--output",
                str(artifacts.profile),
                *common_dates,
                *customer_arguments,
            ),
        ),
        PipelineStep(
            "scope selection",
            (
                sys.executable,
                str(SCRIPTS_DIR / "eda_select_scope.py"),
                "--profile",
                str(artifacts.profile),
                "--output",
                str(artifacts.scope),
                *common_dates,
            ),
        ),
        PipelineStep(
            "scoped load",
            (
                sys.executable,
                str(SCRIPTS_DIR / "load_scoped_data.py"),
                "--source",
                str(settings.source_dir),
                "--manifest",
                str(artifacts.manifest),
                *common_dates,
                "--batch-size",
                str(batch_size),
                *customer_arguments,
            ),
        ),
        PipelineStep(
            "load verification",
            (
                sys.executable,
                str(SCRIPTS_DIR / "verify_load.py"),
                "--source",
                str(settings.source_dir),
                "--manifest",
                str(artifacts.manifest),
            ),
        ),
    )


def _execute_step(step: PipelineStep) -> None:
    print(f"\n==> {step.name}", flush=True)
    subprocess.run(step.command, check=True)


def _require_approved_scope(scope_path: Path) -> None:
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    if not scope.get("approved", False):
        raise RuntimeError(f"EDA scope was not approved; inspect {scope_path}")


def run_pipeline(
    settings: PipelineSettings,
    start_date: date,
    end_date: date,
    batch_size: int,
    customer_ids: tuple[str, ...] = (),
    execute_step: Callable[[PipelineStep], None] = _execute_step,
) -> PipelineArtifacts:
    if start_date > end_date:
        raise ValueError("start-date must be on or before end-date")
    if batch_size < 1:
        raise ValueError("batch-size must be greater than zero")
    if not settings.source_dir.is_dir():
        raise FileNotFoundError(f"DATA_SOURCE_DIR does not exist: {settings.source_dir}")

    settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    settings.manifest_dir.mkdir(parents=True, exist_ok=True)
    artifacts = build_artifacts(settings, start_date, end_date, customer_ids)
    steps = build_steps(
        settings,
        artifacts,
        start_date,
        end_date,
        batch_size,
        customer_ids,
    )

    for index, step in enumerate(steps, start=1):
        print(f"Pipeline progress={index}/{len(steps)} step={step.name}", flush=True)
        execute_step(step)
        if step.name == "scope selection":
            _require_approved_scope(artifacts.scope)

    print("\nPipeline completed", flush=True)
    print(f"Profile: {artifacts.profile}", flush=True)
    print(f"Scope: {artifacts.scope}", flush=True)
    print(f"Manifest: {artifacts.manifest}", flush=True)
    return artifacts


def main() -> None:
    args = parse_args()
    try:
        settings = PipelineSettings.from_environment(os.environ)
        customer_ids = parse_customer_ids(args.customer_ids)
        run_pipeline(
            settings,
            args.start_date,
            args.end_date,
            args.batch_size,
            customer_ids,
        )
    except (FileNotFoundError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"Pipeline failed: {exc}") from exc


if __name__ == "__main__":
    main()
