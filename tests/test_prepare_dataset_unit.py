"""Offline tests for M3 data preparation and structure integration."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd
from requests.exceptions import ProxyError


SCRIPT = Path(__file__).resolve().parents[1] / ".agents/skills/chembl-workflow/scripts/prepare_dataset.py"
SPEC = importlib.util.spec_from_file_location("prepare_dataset", SCRIPT)
prepare_dataset = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(prepare_dataset)


def activity_record(**changes: object) -> dict[str, object]:
    row = {
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
    row.update(changes)
    return row


class PrepareDatasetUnitTest(unittest.TestCase):
    def test_activity_cleaning_drops_missing_and_exact_duplicates_but_keeps_measurements(self) -> None:
        rows = [
            activity_record(),
            activity_record(),
            activity_record(activity_id=2, standard_value="20.0"),
            activity_record(activity_id=3, molecule_chembl_id="CHEMBL26", standard_value="not-a-number"),
            activity_record(activity_id=4, molecule_chembl_id=" "),
        ]

        cleaned, metadata = prepare_dataset.clean_activities(pd.DataFrame(rows))

        self.assertEqual(metadata["raw_activity_rows"], 5)
        self.assertEqual(metadata["dropped_missing_required_fields"], 2)
        self.assertEqual(metadata["dropped_exact_duplicate_rows"], 1)
        self.assertEqual(metadata["numeric_conversion_failures"]["standard_value"], 1)
        self.assertEqual(metadata["aggregation_strategy"], "keep_all")
        self.assertEqual(cleaned["molecule_chembl_id"].tolist(), ["CHEMBL25", "CHEMBL25"])
        self.assertEqual(cleaned["activity_id"].tolist(), [1, 2])
        self.assertEqual(str(cleaned["standard_value"].dtype), "Float64")

    def test_structure_validation_marks_missing_and_invalid_smiles(self) -> None:
        records = [
            {"molecule_chembl_id": "CHEMBL25", "molecule_structures": {"canonical_smiles": "CCO"}},
            {"molecule_chembl_id": "CHEMBL26", "molecule_structures": None},
            {"molecule_chembl_id": "CHEMBL27", "molecule_structures": {"canonical_smiles": "invalid"}},
        ]

        structures, metadata = prepare_dataset.validate_structures(["CHEMBL25", "CHEMBL26", "CHEMBL27"], records)

        self.assertEqual(structures["structure_status"].tolist(), ["valid", "missing_smiles", "invalid_smiles"])
        self.assertEqual(metadata["valid_structures"], 1)
        self.assertEqual(metadata["missing_smiles"], 1)
        self.assertEqual(metadata["invalid_smiles"], 1)

    def test_merge_preserves_repeated_measurements_and_generates_fixed_fingerprints(self) -> None:
        activities, _ = prepare_dataset.clean_activities(
            pd.DataFrame([activity_record(), activity_record(activity_id=2, standard_value="20.0")])
        )
        structures = pd.DataFrame(
            [{"molecule_chembl_id": "CHEMBL25", "canonical_smiles": "CCO", "structure_status": "valid"}]
        )

        prepared, metadata = prepare_dataset.merge_and_fingerprint(activities, structures)

        self.assertEqual(len(prepared), 2)
        self.assertEqual(metadata["activity_rows_lost_no_valid_structure"], 0)
        self.assertTrue(
            prepared["fingerprint"].str.removeprefix("bitstring:").str.len().eq(prepare_dataset.FINGERPRINT_LENGTH).all()
        )

    def test_full_preparation_writes_artifacts_and_metadata(self) -> None:
        raw_activities = pd.DataFrame(
            [
                activity_record(),
                activity_record(activity_id=2, molecule_chembl_id="CHEMBL26", standard_value="20.0"),
            ]
        )
        structure_records = [
            {"molecule_chembl_id": "CHEMBL25", "molecule_structures": {"canonical_smiles": "CCO"}},
            {"molecule_chembl_id": "CHEMBL26", "molecule_structures": None},
        ]

        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            input_csv = directory / "activities.csv"
            output_dir = directory / "prepared"
            raw_activities.to_csv(input_csv, index=False)
            with patch.object(prepare_dataset, "fetch_structure_records", return_value=structure_records):
                report = prepare_dataset.prepare_dataset(input_csv, output_dir, use_cache=False, overwrite=False)

            metadata = json.loads((output_dir / "preparation_metadata.json").read_text(encoding="utf-8"))
            prepared = pd.read_csv(output_dir / "prepared_dataset.csv")

        self.assertEqual(metadata["activity_rows_after_merge"], 1)
        self.assertEqual(metadata["activity_rows_lost_no_valid_structure"], 1)
        self.assertFalse(metadata["client_cache_enabled"])
        self.assertEqual(len(prepared), 1)
        self.assertEqual(
            len(prepared.loc[0, "fingerprint"].removeprefix("bitstring:")),
            prepare_dataset.FINGERPRINT_LENGTH,
        )
        self.assertIn("prepared_dataset_csv", report)

    def test_structure_response_for_wrong_molecule_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "different molecule"):
            prepare_dataset.validate_structures(
                ["CHEMBL25"],
                [{"molecule_chembl_id": "CHEMBL26", "molecule_structures": {"canonical_smiles": "CCO"}}],
            )

    def test_transient_structure_request_retries_once(self) -> None:
        molecule = SimpleNamespace(
            get=Mock(
                side_effect=[
                    ProxyError("connection reset"),
                    {"molecule_chembl_id": "CHEMBL25", "molecule_structures": {"canonical_smiles": "CCO"}},
                ]
            )
        )
        original_client = prepare_dataset.new_client
        try:
            prepare_dataset.new_client = SimpleNamespace(molecule=molecule)
            with patch.object(prepare_dataset.time, "sleep") as sleep:
                records = prepare_dataset.fetch_structure_records(["CHEMBL25"], use_cache=False)
        finally:
            prepare_dataset.new_client = original_client

        self.assertEqual(records[0]["molecule_chembl_id"], "CHEMBL25")
        self.assertEqual(molecule.get.call_count, 2)
        sleep.assert_called_once_with(1)
