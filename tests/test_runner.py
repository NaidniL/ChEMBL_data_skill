"""Tests for the presentation-layer workflow runner."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.workflow import runner


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class WorkflowRunnerTest(unittest.TestCase):
    def test_available_offline_fixtures_are_discovered_from_the_fixture_root(self) -> None:
        self.assertIn("egfr-limit20", runner.available_offline_fixtures(PROJECT_ROOT))

    def test_multiple_live_candidates_require_explicit_selection(self) -> None:
        candidates = [
            {"target_chembl_id": "CHEMBL1", "organism": "Human", "pref_name": "A", "target_type": "SINGLE PROTEIN"},
            {"target_chembl_id": "CHEMBL2", "organism": "Human", "pref_name": "B", "target_type": "SINGLE PROTEIN"},
        ]
        with patch.object(runner, "_run_cli", return_value={"candidates": candidates}):
            with self.assertRaises(runner.TargetSelectionRequired) as raised:
                runner.resolve_target("human EGFR", PROJECT_ROOT)

        self.assertEqual(raised.exception.candidates, candidates)

    def test_offline_fixture_runs_the_deterministic_cli_pipeline(self) -> None:
        progress: list[str] = []
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = runner.run_workflow(
                target="",
                activity_type="IC50",
                source="offline",
                project_root=PROJECT_ROOT,
                runs_root=Path(temporary_directory) / "runs",
                progress=progress.append,
            )

            self.assertTrue(result.validation_report["valid"])
            self.assertEqual(result.target_chembl_id, "CHEMBL203")
            self.assertEqual(result.run_directory.parent, Path(temporary_directory) / "runs")
            self.assertTrue((result.run_directory / "validation/run_manifest.json").is_file())

        self.assertIn("Preparing activities, structures, and fingerprints", progress)
        self.assertIn("Independently validating the completed run", progress)

    def test_offline_fixture_must_be_directly_under_fixture_root(self) -> None:
        with self.assertRaisesRegex(ValueError, "directly under tests/fixtures"):
            runner.run_workflow("", "IC50", "offline", offline_fixture="../outside", project_root=PROJECT_ROOT)

    def test_live_limit_is_forwarded_to_m2(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with (
                patch.object(runner, "resolve_target", return_value={"target_chembl_id": "CHEMBL203"}),
                patch.object(runner, "_run_cli") as invoke_cli,
                patch.object(runner, "_read_artifacts", return_value=object()),
            ):
                runner.run_workflow(
                    target="CHEMBL203",
                    activity_type="IC50",
                    source="live",
                    limit=25,
                    project_root=PROJECT_ROOT,
                    runs_root=Path(temporary_directory) / "runs",
                )

        fetch_call = next(call for call in invoke_cli.call_args_list if call.args[0] == "fetch_activities.py")
        self.assertEqual(fetch_call.args[1][-2:], ["--limit", "25"])

    def test_limit_must_be_a_positive_integer(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive integer"):
            runner.run_workflow("CHEMBL203", "IC50", "live", limit=0, project_root=PROJECT_ROOT)
