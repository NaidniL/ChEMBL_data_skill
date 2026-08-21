"""Offline tests for M4 IC50 normalization, pIC50, statistics, and rankings."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


SCRIPT = Path(__file__).resolve().parents[1] / ".agents/skills/engineering-workflow/scripts/analyze_dataset.py"
SPEC = importlib.util.spec_from_file_location("analyze_dataset", SCRIPT)
analyze_dataset = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(analyze_dataset)


def prepared_record(**changes: object) -> dict[str, object]:
    record = {
        "activity_id": 1,
        "molecule_chembl_id": "CHEMBL25",
        "target_chembl_id": "CHEMBL203",
        "assay_chembl_id": "CHEMBL1",
        "standard_type": "IC50",
        "standard_relation": "=",
        "standard_value": "1",
        "standard_units": "nM",
        "data_validity_comment": None,
        "canonical_smiles": "CCO",
        "fingerprint": "bitstring:0",
    }
    record.update(changes)
    return record


class AnalyzeDatasetUnitTest(unittest.TestCase):
    def test_exact_supported_ic50_values_are_normalized_and_transformed(self) -> None:
        frame = pd.DataFrame(
            [
                prepared_record(activity_id=1, standard_value="1", standard_units="nM"),
                prepared_record(activity_id=2, standard_value="100", standard_units="nM"),
                prepared_record(activity_id=3, standard_value="1", standard_units="uM"),
            ]
        )

        analyzed, metadata = analyze_dataset.analyze_ic50(frame, "IC50")

        self.assertEqual(analyzed["standard_value"].tolist(), ["1", "100", "1"])
        self.assertEqual(analyzed["standard_units"].tolist(), ["nM", "nM", "uM"])
        self.assertEqual(analyzed["ic50_nM"].tolist(), [1.0, 100.0, 1000.0])
        self.assertEqual(analyzed["pIC50"].round(6).tolist(), [9.0, 7.0, 6.0])
        self.assertEqual(metadata["statistics"]["pIC50"]["count"], 3)

    def test_non_comparable_records_are_excluded_by_reason(self) -> None:
        frame = pd.DataFrame(
            [
                prepared_record(),
                prepared_record(activity_id=2, standard_relation=">"),
                prepared_record(activity_id=3, standard_value=None),
                prepared_record(activity_id=4, standard_value="not-a-number"),
                prepared_record(activity_id=5, standard_value="0"),
                prepared_record(activity_id=6, standard_units="mg"),
                prepared_record(activity_id=7, standard_type="Ki"),
                prepared_record(activity_id=8, data_validity_comment="Outside typical range"),
            ]
        )

        analyzed, metadata = analyze_dataset.analyze_ic50(frame, "IC50")

        self.assertEqual(analyzed["activity_id"].tolist(), [1])
        self.assertEqual(
            metadata["exclusions"],
            {
                "wrong_activity_type": 1,
                "non_exact_relation": 1,
                "outside_typical_range": 1,
                "missing_standard_value": 1,
                "invalid_standard_value": 1,
                "non_positive_standard_value": 1,
                "unsupported_or_missing_unit": 1,
            },
        )

    def test_unknown_validity_comment_requires_review(self) -> None:
        frame = pd.DataFrame([prepared_record(data_validity_comment="Unverified assay condition")])

        with self.assertRaisesRegex(ValueError, "Unknown data_validity_comment values require review"):
            analyze_dataset.analyze_ic50(frame, "IC50")

    def test_supported_unit_variants_are_converted_to_nm(self) -> None:
        frame = pd.DataFrame(
            [
                prepared_record(activity_id=1, standard_value="1000", standard_units="pM"),
                prepared_record(activity_id=2, standard_value="1", standard_units="µM"),
                prepared_record(activity_id=3, standard_value="1", standard_units="μM"),
                prepared_record(activity_id=4, standard_value="0.001", standard_units="mM"),
            ]
        )

        analyzed, _ = analyze_dataset.analyze_ic50(frame, "IC50")

        self.assertEqual(analyzed["ic50_nM"].tolist(), [1.0, 1000.0, 1000.0, 1000.0])

    def test_analysis_writes_statistics_and_scientific_rankings(self) -> None:
        frame = pd.DataFrame(
            [
                prepared_record(activity_id=1, standard_value="1", standard_units="nM"),
                prepared_record(activity_id=2, standard_value="100", standard_units="nM"),
                prepared_record(activity_id=3, standard_value="1", standard_units="uM"),
            ]
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            input_csv = directory / "prepared_dataset.csv"
            output_dir = directory / "analysis"
            frame.to_csv(input_csv, index=False)
            report = analyze_dataset.write_analysis(input_csv, output_dir, "IC50", top_n=2, overwrite=False)
            statistics = json.loads((output_dir / "statistics.json").read_text(encoding="utf-8"))
            top_records = pd.read_csv(output_dir / "top_records.csv")
            bottom_records = pd.read_csv(output_dir / "bottom_records.csv")

        self.assertEqual(statistics["statistics"]["pIC50"]["median"], 7.0)
        self.assertEqual(statistics["statistics"]["pIC50"]["minimum"], 6.0)
        self.assertEqual(statistics["statistics"]["pIC50"]["maximum"], 9.0)
        self.assertEqual(top_records["activity_id"].tolist(), [1, 2])
        self.assertEqual(bottom_records["activity_id"].tolist(), [3, 2])
        self.assertEqual(report["ranking"]["metric"], "pIC50")

    def test_only_ic50_is_accepted_by_the_cli(self) -> None:
        with self.assertRaises(SystemExit) as error:
            with patch.object(
                analyze_dataset.sys,
                "argv",
                [str(SCRIPT), "--prepared-csv", "input.csv", "--output-dir", "output", "--activity-type", "Ki"],
            ):
                analyze_dataset.parse_args()

        self.assertEqual(error.exception.code, 2)
