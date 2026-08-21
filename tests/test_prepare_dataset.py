"""Live integration test for M3 preparation with one ChEMBL molecule."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / ".agents/skills/chembl-workflow/scripts/prepare_dataset.py"


class PrepareDatasetTest(unittest.TestCase):
    def test_known_molecule_produces_a_prepared_fingerprint(self) -> None:
        raw_row = {
            "activity_id": 1,
            "molecule_chembl_id": "CHEMBL25",
            "target_chembl_id": "CHEMBL203",
            "assay_chembl_id": "CHEMBL1",
            "standard_type": "IC50",
            "standard_relation": "=",
            "standard_value": "10.0",
            "standard_units": "nM",
            "pchembl_value": "8.0",
            "data_validity_comment": None,
            "potential_duplicate": 0,
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            input_csv = directory / "activities.csv"
            output_dir = directory / "prepared"
            pd.DataFrame([raw_row]).to_csv(input_csv, index=False)
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--activities-csv", str(input_csv), "--output-dir", str(output_dir)],
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
            )
            report = json.loads(completed.stdout)
            metadata = json.loads((output_dir / "preparation_metadata.json").read_text(encoding="utf-8"))
            prepared = pd.read_csv(output_dir / "prepared_dataset.csv")

        self.assertEqual(report["activity_rows_after_merge"], 1)
        self.assertFalse(metadata["client_cache_enabled"])
        self.assertEqual(len(prepared), 1)
        self.assertEqual(len(prepared.loc[0, "fingerprint"].removeprefix("bitstring:")), 2048)
