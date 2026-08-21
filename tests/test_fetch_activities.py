"""Live integration test for raw ChEMBL activity acquisition."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / ".agents/skills/chembl-workflow/scripts/fetch_activities.py"


class FetchActivitiesTest(unittest.TestCase):
    def test_chembl203_ic50_saves_raw_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--target-chembl-id",
                    "CHEMBL203",
                    "--activity-type",
                    "IC50",
                    "--output-dir",
                    str(output_dir),
                    "--limit",
                    "5",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
            )
            report = json.loads(completed.stdout)
            metadata = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
            header = (output_dir / "activities.csv").read_text(encoding="utf-8").splitlines()[0].split(",")

        self.assertGreater(report["record_count"], 0)
        self.assertLessEqual(report["record_count"], 5)
        self.assertEqual(metadata["target_chembl_id"], "CHEMBL203")
        self.assertEqual(metadata["activity_type"], "IC50")
        self.assertFalse(metadata["client_cache_enabled"])
        self.assertEqual(metadata["cache_policy"], "disabled by default; enable only with --use-cache")
        self.assertEqual(header, metadata["columns"])
