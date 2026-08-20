"""Offline behavior tests for raw ChEMBL activity acquisition."""

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from requests.exceptions import ProxyError


SCRIPT = Path(__file__).resolve().parents[1] / ".agents/skills/engineering-workflow/scripts/fetch_activities.py"
SPEC = importlib.util.spec_from_file_location("fetch_activities", SCRIPT)
fetch_activities = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(fetch_activities)


def activity_record(**changes: object) -> dict[str, object]:
    record = {
        "activity_id": "1",
        "molecule_chembl_id": "CHEMBL25",
        "target_chembl_id": "CHEMBL203",
        "assay_chembl_id": "CHEMBL1",
        "standard_type": "IC50",
        "standard_relation": "=",
        "standard_value": "50.0",
        "standard_units": "nM",
        "pchembl_value": "7.30",
        "data_validity_comment": None,
        "potential_duplicate": 0,
    }
    record.update(changes)
    return record


class FetchActivitiesUnitTest(unittest.TestCase):
    def test_malformed_target_id_is_rejected(self) -> None:
        with (
            patch.object(fetch_activities.sys, "argv", [str(SCRIPT), "--target-chembl-id", "EGFR", "--activity-type", "IC50", "--output-dir", "output"]),
            redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as error,
        ):
            fetch_activities.parse_args()

        self.assertEqual(error.exception.code, 2)

    def test_blank_activity_type_is_rejected(self) -> None:
        with (
            patch.object(fetch_activities.sys, "argv", [str(SCRIPT), "--target-chembl-id", "CHEMBL203", "--activity-type", "   ", "--output-dir", "output"]),
            redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as error,
        ):
            fetch_activities.parse_args()

        self.assertEqual(error.exception.code, 2)

    def test_use_cache_is_opt_in(self) -> None:
        with patch.object(
            fetch_activities.sys,
            "argv",
            [
                str(SCRIPT),
                "--target-chembl-id",
                "CHEMBL203",
                "--activity-type",
                "IC50",
                "--output-dir",
                "output",
                "--use-cache",
            ],
        ):
            args = fetch_activities.parse_args()

        self.assertTrue(args.use_cache)

    def test_saves_unmodified_raw_records_and_metadata(self) -> None:
        result = Mock()
        result.only.return_value = [activity_record()]
        activity_api = Mock(filter=Mock(return_value=result))

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory)
            with patch.object(fetch_activities, "new_client", SimpleNamespace(activity=activity_api)):
                report = fetch_activities.save_raw_dataset("CHEMBL203", "IC50", output_dir, overwrite=False)

            metadata = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
            csv_lines = (output_dir / "activities.csv").read_text(encoding="utf-8").splitlines()

        activity_api.filter.assert_called_once_with(target_chembl_id="CHEMBL203", standard_type="IC50")
        result.only.assert_called_once_with(*fetch_activities.RAW_ACTIVITY_COLUMNS)
        self.assertEqual(report["record_count"], 1)
        self.assertEqual(metadata["target_chembl_id"], "CHEMBL203")
        self.assertEqual(metadata["activity_type"], "IC50")
        self.assertEqual(metadata["columns"], list(fetch_activities.RAW_ACTIVITY_COLUMNS))
        self.assertFalse(metadata["client_cache_enabled"])
        self.assertEqual(metadata["cache_policy"], "disabled by default; enable only with --use-cache")
        self.assertEqual(csv_lines[0].split(","), list(fetch_activities.RAW_ACTIVITY_COLUMNS))
        self.assertIn("CHEMBL25", csv_lines[1])

    def test_cache_setting_is_configured_before_client_import(self) -> None:
        result = Mock()
        result.only.return_value = [activity_record()]
        client = SimpleNamespace(activity=Mock(filter=Mock(return_value=result)))
        settings = SimpleNamespace(CACHING=True)
        client_module = ModuleType("chembl_webresource_client.new_client")
        client_module.new_client = client
        original_client = fetch_activities.new_client

        try:
            fetch_activities.new_client = None
            with (
                patch("chembl_webresource_client.settings.Settings.Instance", return_value=settings),
                patch.dict(sys.modules, {"chembl_webresource_client.new_client": client_module}),
            ):
                fetch_activities.fetch_records("CHEMBL203", "IC50", use_cache=False)
        finally:
            fetch_activities.new_client = original_client

        self.assertFalse(settings.CACHING)

    def test_empty_requested_property_fails(self) -> None:
        result = Mock()
        result.only.return_value = []
        activity_api = Mock(filter=Mock(return_value=result))

        with patch.object(fetch_activities, "new_client", SimpleNamespace(activity=activity_api)):
            with self.assertRaisesRegex(ValueError, "No IC50 activity records"):
                fetch_activities.fetch_records("CHEMBL203", "IC50")

    def test_transient_api_error_retries_once_then_returns_records(self) -> None:
        result = Mock()
        result.only.return_value = [activity_record()]
        activity_api = Mock(filter=Mock(side_effect=[ProxyError("connection reset"), result]))

        with (
            patch.object(fetch_activities, "new_client", SimpleNamespace(activity=activity_api)),
            patch.object(fetch_activities.time, "sleep") as sleep,
        ):
            records = fetch_activities.fetch_records("CHEMBL203", "IC50")

        self.assertEqual(records, [activity_record()])
        self.assertEqual(activity_api.filter.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_missing_raw_schema_field_fails(self) -> None:
        record = activity_record()
        del record["pchembl_value"]
        result = Mock()
        result.only.return_value = [record]
        activity_api = Mock(filter=Mock(return_value=result))

        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch.object(fetch_activities, "new_client", SimpleNamespace(activity=activity_api)):
                with self.assertRaisesRegex(ValueError, "pchembl_value"):
                    fetch_activities.save_raw_dataset("CHEMBL203", "IC50", Path(temporary_directory), overwrite=False)

    def test_mismatched_target_or_activity_type_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "target_chembl_id different"):
            fetch_activities.validate_raw_frame(
                fetch_activities.pd.DataFrame([activity_record(target_chembl_id="CHEMBL204")]),
                "CHEMBL203",
                "IC50",
            )
        with self.assertRaisesRegex(ValueError, "standard_type different"):
            fetch_activities.validate_raw_frame(
                fetch_activities.pd.DataFrame([activity_record(standard_type="Ki")]),
                "CHEMBL203",
                "IC50",
            )
