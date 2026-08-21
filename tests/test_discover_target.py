"""Live integration test for ChEMBL target discovery."""

import json
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / ".agents/skills/chembl-workflow/scripts/discover_target.py"


class DiscoverTargetTest(unittest.TestCase):
    def test_uniprot_p00533_returns_structured_candidates(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--uniprot-accession", "P00533"],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        payload = json.loads(completed.stdout)

        self.assertEqual(payload["query"]["identifier_type"], "uniprot_accession")
        self.assertEqual(payload["query"]["value"], "P00533")
        self.assertIsInstance(payload["candidates"], list)
        self.assertTrue(payload["candidates"])
        self.assertIn("CHEMBL203", {candidate["target_chembl_id"] for candidate in payload["candidates"]})
        self.assertTrue(all(set(candidate) == {"target_chembl_id", "organism", "pref_name", "target_type"} for candidate in payload["candidates"]))
