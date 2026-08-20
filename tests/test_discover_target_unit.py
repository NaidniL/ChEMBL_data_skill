"""Offline behavior tests for ChEMBL target discovery."""

import argparse
import copy
import io
import unittest
from contextlib import redirect_stderr
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pathlib import Path
import importlib.util


SCRIPT = Path(__file__).resolve().parents[1] / ".agents/skills/engineering-workflow/scripts/discover_target.py"
SPEC = importlib.util.spec_from_file_location("discover_target", SCRIPT)
discover_target = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(discover_target)


class DiscoverTargetUnitTest(unittest.TestCase):
    def test_empty_target_name_is_rejected(self) -> None:
        with (
            patch.object(discover_target.sys, "argv", [str(SCRIPT), "--target-name", ""]),
            redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as error,
        ):
            discover_target.parse_args()

        self.assertEqual(error.exception.code, 2)

    def test_whitespace_target_name_is_rejected(self) -> None:
        with (
            patch.object(discover_target.sys, "argv", [str(SCRIPT), "--target-name", "   "]),
            redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as error,
        ):
            discover_target.parse_args()

        self.assertEqual(error.exception.code, 2)

    def test_malformed_chembl_target_id_is_rejected(self) -> None:
        with (
            patch.object(discover_target.sys, "argv", [str(SCRIPT), "--chembl-target-id", "EGFR"]),
            redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as error,
        ):
            discover_target.parse_args()

        self.assertEqual(error.exception.code, 2)

    def test_target_name_is_sent_as_a_name_lookup(self) -> None:
        with patch.object(discover_target.sys, "argv", [str(SCRIPT), "--target-name", "EGFR"]):
            args = discover_target.parse_args()

        identifier_type, value, query = discover_target.target_query(args)
        self.assertEqual(identifier_type, "target_name")
        self.assertEqual(value, "EGFR")
        self.assertEqual(query, {"pref_name": "EGFR"})

    def test_no_match_returns_an_empty_candidate_list(self) -> None:
        result = Mock()
        result.only.return_value = []
        target_api = Mock(get=Mock(return_value=result))
        args = argparse.Namespace(
            target_name=None,
            uniprot_accession=None,
            chembl_target_id="CHEMBL999999999",
            organism=None,
        )

        with patch.object(discover_target, "new_client", SimpleNamespace(target=target_api)):
            payload = discover_target.discover_targets(args)

        self.assertEqual(payload["candidates"], [])
        target_api.get.assert_called_once_with(target_chembl_id="CHEMBL999999999")

    def test_multiple_candidates_are_returned_unchanged(self) -> None:
        candidates = [
            {
                "target_chembl_id": "CHEMBL203",
                "organism": "Homo sapiens",
                "pref_name": "Epidermal growth factor receptor",
                "target_type": "SINGLE PROTEIN",
            },
            {
                "target_chembl_id": "CHEMBL4523747",
                "organism": "Homo sapiens",
                "pref_name": "EGFR/PPP1CA",
                "target_type": "PROTEIN COMPLEX",
            },
        ]
        original_candidates = copy.deepcopy(candidates)
        result = Mock()
        result.only.return_value = candidates
        target_api = Mock(get=Mock(return_value=result))
        args = argparse.Namespace(
            target_name=None,
            uniprot_accession="P00533",
            chembl_target_id=None,
            organism="Homo sapiens",
        )

        with patch.object(discover_target, "new_client", SimpleNamespace(target=target_api)):
            payload = discover_target.discover_targets(args)

        target_api.get.assert_called_once_with(
            target_components__accession="P00533",
            organism="Homo sapiens",
        )
        result.only.assert_called_once_with(*discover_target.CANDIDATE_FIELDS)
        self.assertEqual(payload["candidates"], original_candidates)
        self.assertEqual(candidates, original_candidates)

    def test_api_failure_is_reported_without_a_fallback_candidate(self) -> None:
        target_api = Mock(get=Mock(side_effect=RuntimeError("HTTP 503 Service Unavailable")))
        stderr = io.StringIO()

        with (
            patch.object(discover_target, "new_client", SimpleNamespace(target=target_api)),
            patch.object(
                discover_target.sys,
                "argv",
                [str(SCRIPT), "--chembl-target-id", "CHEMBL203"],
            ),
            redirect_stderr(stderr),
        ):
            exit_code = discover_target.main()

        self.assertEqual(exit_code, 2)
        self.assertIn("ChEMBL target query failed: HTTP 503 Service Unavailable", stderr.getvalue())
        target_api.get.assert_called_once_with(target_chembl_id="CHEMBL203")
