"""Orchestrate the deterministic M1-M5 workflow for the Streamlit presentation layer."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OFFLINE_REQUIRED_FILES = ("activities.csv", "metadata.json", "structures.csv")
UNIPROT_ACCESSION = re.compile(r"^[A-Z0-9]{6,10}$")
ProgressCallback = Callable[[str], None]


class WorkflowExecutionError(RuntimeError):
    """A deterministic CLI stage could not complete."""


class TargetSelectionRequired(WorkflowExecutionError):
    """Target discovery returned more than one candidate."""

    def __init__(self, candidates: list[dict[str, Any]]) -> None:
        super().__init__("Target discovery returned multiple candidates. Select one ChEMBL target ID and run again.")
        self.candidates = candidates


@dataclass(frozen=True)
class WorkflowRun:
    """Completed run directory and artifacts for display."""

    run_directory: Path
    target_chembl_id: str
    source: str
    run_manifest: dict[str, Any]
    validation_report: dict[str, Any]
    statistics: dict[str, Any]
    exclusions: dict[str, Any]
    top_records: pd.DataFrame
    bottom_records: pd.DataFrame


def _run_cli(script_name: str, arguments: list[str], project_root: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(project_root / ".agents/skills/chembl-workflow/scripts" / script_name), *arguments],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no diagnostic output"
        raise WorkflowExecutionError(f"{script_name} failed: {detail}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise WorkflowExecutionError(f"{script_name} returned unreadable JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise WorkflowExecutionError(f"{script_name} returned JSON that is not an object.")
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowExecutionError(f"Required artifact is unreadable: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise WorkflowExecutionError(f"Required artifact must be a JSON object: {path}")
    return payload


def _discovery_arguments(target: str) -> list[str]:
    if not target.strip():
        raise ValueError("Target is required for a live ChEMBL run.")
    if target.upper().startswith("CHEMBL"):
        return ["--chembl-target-id", target]
    if UNIPROT_ACCESSION.fullmatch(target):
        return ["--uniprot-accession", target]
    return ["--target-name", target]


def resolve_target(target: str, project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    """Resolve exactly one candidate; do not select one on the user's behalf."""
    payload = _run_cli("discover_target.py", _discovery_arguments(target), project_root)
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not all(isinstance(candidate, dict) for candidate in candidates):
        raise WorkflowExecutionError("discover_target.py returned an invalid candidates payload.")
    if not candidates:
        raise WorkflowExecutionError("Target discovery returned no candidates. Refine the target identifier and try again.")
    if any(not isinstance(candidate.get("target_chembl_id"), str) or not candidate["target_chembl_id"] for candidate in candidates):
        raise WorkflowExecutionError("Target discovery returned a candidate without target_chembl_id.")
    if len(candidates) != 1:
        raise TargetSelectionRequired(candidates)
    return candidates[0]


def _new_run_directory(runs_root: Path) -> Path:
    run_directory = runs_root / datetime.now().strftime("%Y%m%dT%H%M%S_%f")
    run_directory.mkdir(parents=True, exist_ok=False)
    return run_directory


def available_offline_fixtures(project_root: Path = PROJECT_ROOT) -> list[str]:
    """Return valid fixture directories directly under tests/fixtures."""
    fixtures_dir = project_root / "tests/fixtures"
    if not fixtures_dir.is_dir():
        raise WorkflowExecutionError(f"Offline fixture directory is missing: {fixtures_dir}")
    return sorted(
        path.name
        for path in fixtures_dir.iterdir()
        if path.is_dir() and all((path / filename).is_file() for filename in OFFLINE_REQUIRED_FILES)
    )


def _offline_fixture_directory(fixture_name: str, project_root: Path) -> Path:
    fixtures_dir = (project_root / "tests/fixtures").resolve()
    fixture_dir = (fixtures_dir / fixture_name).resolve()
    if fixture_dir.parent != fixtures_dir or not fixture_dir.is_dir():
        raise ValueError("offline_fixture must name a fixture directory directly under tests/fixtures.")
    missing = [filename for filename in OFFLINE_REQUIRED_FILES if not (fixture_dir / filename).is_file()]
    if missing:
        raise WorkflowExecutionError(f"Offline fixture {fixture_name!r} is missing: {', '.join(missing)}")
    return fixture_dir


def _read_artifacts(run_directory: Path, target_chembl_id: str, source: str) -> WorkflowRun:
    validation_dir = run_directory / "validation"
    analysis_dir = run_directory / "analysis"
    return WorkflowRun(
        run_directory=run_directory,
        target_chembl_id=target_chembl_id,
        source=source,
        run_manifest=_load_json(validation_dir / "run_manifest.json"),
        validation_report=_load_json(validation_dir / "validation_report.json"),
        statistics=_load_json(analysis_dir / "statistics.json"),
        exclusions=_load_json(validation_dir / "exclusions.json"),
        top_records=pd.read_csv(analysis_dir / "top_records.csv"),
        bottom_records=pd.read_csv(analysis_dir / "bottom_records.csv"),
    )


def run_workflow(
    target: str,
    activity_type: str,
    source: str,
    *,
    limit: int | None = 200,
    offline_fixture: str = "egfr-limit20",
    original_target_query: str | None = None,
    project_root: Path = PROJECT_ROOT,
    runs_root: Path | None = None,
    progress: ProgressCallback | None = None,
) -> WorkflowRun:
    """Run the existing deterministic CLI scripts and return their display artifacts."""
    if source not in {"live", "offline"}:
        raise ValueError("source must be either 'live' or 'offline'.")
    if activity_type != "IC50":
        raise ValueError("The current deterministic workflow supports IC50 only.")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
        raise ValueError("limit must be a positive integer or None.")

    report_progress = progress or (lambda _message: None)
    if source == "live":
        report_progress("Resolving target with ChEMBL")
        candidate = resolve_target(target, project_root)
        target_chembl_id = candidate["target_chembl_id"]
        manifest_query = original_target_query or target
    else:
        fixture_dir = _offline_fixture_directory(offline_fixture, project_root)
        raw_metadata = _load_json(fixture_dir / "metadata.json")
        target_chembl_id = raw_metadata.get("target_chembl_id")
        if not isinstance(target_chembl_id, str) or not target_chembl_id:
            raise WorkflowExecutionError("Offline fixture metadata has no target_chembl_id.")
        manifest_query = f"offline fixture: {offline_fixture}"

    run_directory = _new_run_directory(runs_root or project_root / "runs")
    raw_dir = run_directory / "raw"
    prepared_dir = run_directory / "prepared"
    analysis_dir = run_directory / "analysis"
    validation_dir = run_directory / "validation"

    if source == "live":
        report_progress("Retrieving raw activity records")
        fetch_arguments = [
            "--target-chembl-id",
            target_chembl_id,
            "--activity-type",
            activity_type,
            "--output-dir",
            str(raw_dir),
        ]
        if limit is not None:
            fetch_arguments.extend(["--limit", str(limit)])
        _run_cli("fetch_activities.py", fetch_arguments, project_root)
        prepare_arguments = ["--activities-csv", str(raw_dir / "activities.csv"), "--output-dir", str(prepared_dir)]
    else:
        report_progress(f"Copying offline fixture: {offline_fixture}")
        raw_dir.mkdir(parents=True)
        for filename in ("activities.csv", "metadata.json"):
            source_path = fixture_dir / filename
            shutil.copy2(source_path, raw_dir / filename)
        prepare_arguments = [
            "--activities-csv",
            str(raw_dir / "activities.csv"),
            "--structures-csv",
            str(fixture_dir / "structures.csv"),
            "--output-dir",
            str(prepared_dir),
        ]

    report_progress("Preparing activities, structures, and fingerprints")
    _run_cli("prepare_dataset.py", prepare_arguments, project_root)
    report_progress("Normalizing IC50 values and calculating pIC50 statistics")
    _run_cli(
        "analyze_dataset.py",
        [
            "--prepared-csv",
            str(prepared_dir / "prepared_dataset.csv"),
            "--output-dir",
            str(analysis_dir),
            "--activity-type",
            activity_type,
        ],
        project_root,
    )
    report_progress("Building provenance and exclusion artifacts")
    _run_cli(
        "build_run_manifest.py",
        [
            "--original-target-query",
            manifest_query,
            "--raw-activities-csv",
            str(raw_dir / "activities.csv"),
            "--raw-metadata-json",
            str(raw_dir / "metadata.json"),
            "--cleaned-activities-csv",
            str(prepared_dir / "activities_clean.csv"),
            "--structures-csv",
            str(prepared_dir / "structures.csv"),
            "--preparation-metadata-json",
            str(prepared_dir / "preparation_metadata.json"),
            "--prepared-csv",
            str(prepared_dir / "prepared_dataset.csv"),
            "--analyzed-csv",
            str(analysis_dir / "analyzed_dataset.csv"),
            "--statistics-json",
            str(analysis_dir / "statistics.json"),
            "--top-records-csv",
            str(analysis_dir / "top_records.csv"),
            "--bottom-records-csv",
            str(analysis_dir / "bottom_records.csv"),
            "--output-dir",
            str(validation_dir),
        ],
        project_root,
    )
    report_progress("Independently validating the completed run")
    _run_cli(
        "validate_run.py",
        [
            "--run-manifest-json",
            str(validation_dir / "run_manifest.json"),
            "--report-json",
            str(validation_dir / "validation_report.json"),
        ],
        project_root,
    )
    report_progress("Loading generated artifacts")
    return _read_artifacts(run_directory, target_chembl_id, source)
