"""Compatibility exports for dispute replay consumers."""
from banking_evals.disputes.baseline import DeterministicIntake, normalized, run_baseline
from banking_evals.disputes.reports import rescore, case_latency, compare_reports, write_artifacts
from banking_evals.disputes.cli import execute_case, main_async, main

if __name__ == "__main__":
    raise SystemExit(main())
from banking_evals.evidence import sanitize
