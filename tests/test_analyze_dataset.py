"""Subprocess test for M4 analysis artifacts."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / ".agents/skills/engineering-workflow/scripts/analyze_dataset.py"


class AnalyzeDatasetTest(unittest.TestCase):
    def test_cli_writes_analyzed_dataset_and_rankings(self) -> None:
        rows = [
            {
                "activity_id": 1,
                "molecule_chembl_id": "CHEMBL25",
                "standard_type": "IC50",
                "standard_relation": "=",
                "standard_value": "1",
                "standard_units": "nM",
                "data_validity_comment": None,
            },
            {
                "activity_id": 2,
                "molecule_chembl_id": "CHEMBL26",
                "standard_type": "IC50",
                "standard_relation": ">",
                "standard_value": "2",
                "standard_units": "nM",
                "data_validity_comment": None,
            },
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            input_csv = directory / "prepared_dataset.csv"
            output_dir = directory / "analysis"
            pd.DataFrame(rows).to_csv(input_csv, index=False)
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--prepared-csv", str(input_csv), "--output-dir", str(output_dir)],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            report = json.loads(completed.stdout)
            analyzed = pd.read_csv(output_dir / "analyzed_dataset.csv")
            statistics = json.loads((output_dir / "statistics.json").read_text(encoding="utf-8"))

        self.assertEqual(report["analyzed_records"], 1)
        self.assertEqual(analyzed["pIC50"].tolist(), [9.0])
        self.assertEqual(statistics["exclusions"]["non_exact_relation"], 1)
