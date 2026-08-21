"""Offline M5 tests for manifest, exclusion flow, and independent validation."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_script: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


prepare_dataset = load_module("prepare_dataset_m5", ".agents/skills/engineering-workflow/scripts/prepare_dataset.py")
analyze_dataset = load_module("analyze_dataset_m5", ".agents/skills/engineering-workflow/scripts/analyze_dataset.py")
build_run_manifest = load_module("build_run_manifest_m5", ".agents/skills/engineering-workflow/scripts/build_run_manifest.py")
validate_run = load_module("validate_run_m5", ".agents/skills/engineering-workflow/scripts/validate_run.py")


def raw_record(**changes: object) -> dict[str, object]:
    record = {
        "activity_id": 1,
        "molecule_chembl_id": "CHEMBL25",
        "target_chembl_id": "CHEMBL203",
        "assay_chembl_id": "CHEMBL1",
        "standard_type": "IC50",
        "standard_relation": "=",
        "standard_value": "10",
        "standard_units": "nM",
        "pchembl_value": "8",
        "data_validity_comment": None,
        "potential_duplicate": 0,
    }
    record.update(changes)
    return record


class M5ValidationUnitTest(unittest.TestCase):
    def create_valid_run(self, directory: Path) -> dict[str, Path]:
        raw_dir = directory / "raw"
        prepared_dir = directory / "prepared"
        analysis_dir = directory / "analysis"
        manifest_dir = directory / "manifest"
        raw_dir.mkdir()
        raw_csv = raw_dir / "activities.csv"
        raw_metadata = raw_dir / "metadata.json"
        pd.DataFrame([raw_record(), raw_record(), raw_record(activity_id=2, molecule_chembl_id="CHEMBL26", standard_relation=">")]).to_csv(raw_csv, index=False)
        raw_metadata.write_text(
            json.dumps(
                {
                    "target_chembl_id": "CHEMBL203",
                    "activity_type": "IC50",
                    "record_count": 3,
                    "columns": list(prepare_dataset.ACTIVITY_COLUMNS),
                    "client_cache_enabled": False,
                }
            ),
            encoding="utf-8",
        )
        structures = [
            {"molecule_chembl_id": "CHEMBL25", "molecule_structures": {"canonical_smiles": "CCO"}},
            {"molecule_chembl_id": "CHEMBL26", "molecule_structures": {"canonical_smiles": "CCN"}},
        ]
        with patch.object(prepare_dataset, "fetch_structure_records", return_value=structures):
            prepare_dataset.prepare_dataset(raw_csv, prepared_dir, use_cache=False, overwrite=False)
        analyze_dataset.write_analysis(
            prepared_dir / "prepared_dataset.csv",
            analysis_dir,
            "IC50",
            top_n=1,
            overwrite=False,
        )
        build_run_manifest.build_manifest(
            raw_activities_csv=raw_csv,
            raw_metadata_json=raw_metadata,
            cleaned_activities_csv=prepared_dir / "activities_clean.csv",
            structures_csv=prepared_dir / "structures.csv",
            preparation_metadata_json=prepared_dir / "preparation_metadata.json",
            prepared_csv=prepared_dir / "prepared_dataset.csv",
            analyzed_csv=analysis_dir / "analyzed_dataset.csv",
            statistics_json=analysis_dir / "statistics.json",
            top_records_csv=analysis_dir / "top_records.csv",
            bottom_records_csv=analysis_dir / "bottom_records.csv",
            output_dir=manifest_dir,
            original_target_query="P00533",
            overwrite=False,
        )
        return {
            "raw_csv": raw_csv,
            "structures_csv": prepared_dir / "structures.csv",
            "prepared_csv": prepared_dir / "prepared_dataset.csv",
            "analyzed_csv": analysis_dir / "analyzed_dataset.csv",
            "preparation_metadata": prepared_dir / "preparation_metadata.json",
            "exclusions": manifest_dir / "exclusions.json",
            "manifest": manifest_dir / "run_manifest.json",
        }

    def test_builds_reconciled_exclusions_and_validates_a_complete_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            paths = self.create_valid_run(Path(temporary_directory))
            exclusions = json.loads(paths["exclusions"].read_text(encoding="utf-8"))
            report = validate_run.validate_run(paths["manifest"])

        self.assertTrue(report["valid"])
        self.assertEqual(exclusions["records"][1]["newly_excluded_records"], 0)
        self.assertEqual(exclusions["records"][2]["newly_excluded_records"], 1)
        self.assertEqual(exclusions["records"][5]["newly_excluded_records"], 1)
        self.assertEqual(exclusions["final_analyzed_records"], 1)
        self.assertIn("Validation passed", report["message"])

    def test_reports_invalid_artifacts_with_specific_remediation(self) -> None:
        cases = {
            "raw_schema": lambda paths: pd.read_csv(paths["raw_csv"]).drop(columns=["target_chembl_id"]).to_csv(paths["raw_csv"], index=False),
            "valid_smiles": lambda paths: self.write_cell(paths["structures_csv"], "canonical_smiles", "invalid"),
            "fingerprint_encoding": lambda paths: self.write_cell(paths["prepared_csv"], "fingerprint", "bitstring:101"),
            "unknown_validity_comment": lambda paths: self.write_cell(paths["prepared_csv"], "data_validity_comment", "Needs review"),
            "pic50_transformation": lambda paths: self.write_cell(paths["analyzed_csv"], "pIC50", 99.0),
            "exclusion_reconciliation": lambda paths: self.break_exclusion_transition(paths["exclusions"]),
        }
        for expected_check, mutate in cases.items():
            with self.subTest(expected_check=expected_check), tempfile.TemporaryDirectory() as temporary_directory:
                paths = self.create_valid_run(Path(temporary_directory))
                mutate(paths)
                report = validate_run.validate_run(paths["manifest"])

                self.assertFalse(report["valid"])
                self.assertIn(expected_check, {error["check"] for error in report["errors"]})
                self.assertTrue(all(error["remediation"] for error in report["errors"]))

    @staticmethod
    def write_cell(path: Path, column: str, value: object) -> None:
        frame = pd.read_csv(path)
        if isinstance(value, str) and pd.api.types.is_numeric_dtype(frame[column]):
            frame[column] = frame[column].astype("object")
        frame.loc[0, column] = value
        frame.to_csv(path, index=False)

    @staticmethod
    def break_exclusion_transition(path: Path) -> None:
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["records"][2]["output_records"] = 99
        path.write_text(json.dumps(payload), encoding="utf-8")
