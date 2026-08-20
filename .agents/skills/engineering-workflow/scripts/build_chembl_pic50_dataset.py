#!/usr/bin/env python3
"""Build a ChEMBL IC50/pIC50 dataset with RDKit Morgan fingerprints."""

from __future__ import annotations

import argparse
import json
import math
import sys
from http.client import RemoteDisconnected
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://www.ebi.ac.uk/chembl/api/data"
API_ORIGIN = "https://www.ebi.ac.uk"
UNIT_TO_NM = {"PM": 0.001, "NM": 1.0, "UM": 1000.0, "MM": 1000000.0}


def get_json(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    query = f"?{urlencode(params, doseq=True)}" if params else ""
    if path.startswith("http"):
        url = path
    elif path.startswith("/chembl/api/data/"):
        url = f"{API_ORIGIN}{path}"
    else:
        url = f"{BASE_URL}{path}{query}"
    try:
        request = Request(url, headers={"Accept": "application/json", "User-Agent": "engineering-workflow/0.1"})
        with urlopen(request, timeout=60) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"ChEMBL API returned HTTP {exc.code} for {url}") from exc
    except (RemoteDisconnected, URLError, OSError) as exc:
        raise RuntimeError(f"Could not reach the ChEMBL API: {getattr(exc, 'reason', exc)}") from exc


def list_targets(target: str) -> None:
    payload = get_json("/target/search.json", {"q": target, "limit": 20})
    candidates = [
        {
            "target_chembl_id": item.get("target_chembl_id"),
            "pref_name": item.get("pref_name"),
            "organism": item.get("organism"),
            "target_type": item.get("target_type"),
            "score": item.get("score"),
        }
        for item in payload.get("targets", [])
    ]
    print(json.dumps({"query": target, "candidates": candidates}, indent=2))


def fetch_activities(target_id: str) -> list[dict[str, Any]]:
    payload = get_json(
        "/activity.json",
        {"target_chembl_id": target_id, "standard_type": "IC50", "limit": 1000},
    )
    activities = payload.get("activities", [])
    next_page = payload.get("page_meta", {}).get("next")
    while next_page:
        payload = get_json(next_page)
        activities.extend(payload.get("activities", []))
        next_page = payload.get("page_meta", {}).get("next")
    if not activities:
        raise ValueError(f"No ChEMBL IC50 activities were returned for {target_id}.")
    return activities


def canonical_smiles(molecule_id: str) -> str | None:
    molecule = get_json(f"/molecule/{molecule_id}.json")
    structures = molecule.get("molecule_structures") or {}
    return structures.get("canonical_smiles")


def count_and_filter(frame: Any, mask: Any, statistics: dict[str, Any], reason: str) -> Any:
    statistics["exclusions"][reason] = int((~mask).sum())
    return frame.loc[mask].copy()


def build_dataset(target_id: str, output_dir: Path, overwrite: bool) -> None:
    try:
        import pandas as pd
        from rdkit import Chem
        from rdkit.Chem import rdFingerprintGenerator
    except ImportError as exc:
        raise RuntimeError("Install dependencies with `python -m pip install -r requirements.txt`.") from exc

    dataset_path = output_dir / "dataset.csv"
    statistics_path = output_dir / "statistics.json"
    existing = [path for path in (dataset_path, statistics_path) if path.exists()]
    if existing and not overwrite:
        names = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Refusing to overwrite {names}. Re-run with --overwrite.")

    frame = pd.DataFrame(fetch_activities(target_id))
    required_columns = {
        "activity_id",
        "molecule_chembl_id",
        "standard_type",
        "standard_relation",
        "standard_value",
        "standard_units",
        "data_validity_comment",
        "canonical_smiles",
        "target_chembl_id",
        "target_pref_name",
    }
    missing_columns = sorted(required_columns.difference(frame.columns))
    if missing_columns:
        raise ValueError(f"ChEMBL activity response lacks required fields: {', '.join(missing_columns)}")

    statistics: dict[str, Any] = {
        "target_chembl_id": target_id,
        "source_records": int(len(frame)),
        "exclusions": {},
        "fingerprint": {"type": "Morgan", "radius": 2, "n_bits": 2048},
    }

    frame = count_and_filter(
        frame,
        frame[["molecule_chembl_id", "standard_value", "standard_units"]].notna().all(axis=1),
        statistics,
        "missing_required_field",
    )
    frame = count_and_filter(frame, frame["standard_type"].eq("IC50"), statistics, "not_ic50")
    frame = count_and_filter(frame, frame["standard_relation"].eq("="), statistics, "non_exact_relation")
    frame = count_and_filter(
        frame,
        frame["data_validity_comment"].isna() | frame["data_validity_comment"].eq(""),
        statistics,
        "data_validity_flag",
    )
    frame["standard_value"] = pd.to_numeric(frame["standard_value"], errors="coerce")
    frame = count_and_filter(frame, frame["standard_value"].gt(0), statistics, "invalid_ic50_value")
    frame["unit_key"] = (
        frame["standard_units"].astype(str).str.strip().str.upper().str.replace("µ", "U", regex=False)
    )
    frame = count_and_filter(frame, frame["unit_key"].isin(UNIT_TO_NM), statistics, "unsupported_unit")

    missing_smiles = frame["canonical_smiles"].isna() | frame["canonical_smiles"].eq("")
    molecule_ids = frame.loc[missing_smiles, "molecule_chembl_id"].drop_duplicates()
    structure_map = {molecule_id: canonical_smiles(molecule_id) for molecule_id in molecule_ids}
    frame.loc[missing_smiles, "canonical_smiles"] = frame.loc[missing_smiles, "molecule_chembl_id"].map(structure_map)
    statistics["structure_api_requests"] = len(structure_map)
    frame = count_and_filter(
        frame,
        frame["canonical_smiles"].notna() & frame["canonical_smiles"].ne(""),
        statistics,
        "missing_canonical_smiles",
    )

    frame["mol"] = frame["canonical_smiles"].map(Chem.MolFromSmiles)
    frame = count_and_filter(frame, frame["mol"].notna(), statistics, "invalid_smiles")
    frame["ic50_nM"] = frame["standard_value"] * frame["unit_key"].map(UNIT_TO_NM)
    frame["pIC50"] = frame["ic50_nM"].map(lambda value: 9 - math.log10(value))

    fingerprint_generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    frame["fingerprint"] = frame["mol"].map(lambda molecule: fingerprint_generator.GetFingerprint(molecule).ToBitString())
    frame = frame.sort_values(["pIC50", "activity_id"], ascending=[False, True])
    output_columns = [
        "activity_id",
        "molecule_chembl_id",
        "target_chembl_id",
        "target_pref_name",
        "standard_value",
        "standard_units",
        "ic50_nM",
        "pIC50",
        "canonical_smiles",
        "fingerprint",
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    frame.loc[:, output_columns].to_csv(dataset_path, index=False)
    statistics["accepted_records"] = int(len(frame))
    statistics["pic50"] = {
        "min": float(frame["pIC50"].min()),
        "max": float(frame["pIC50"].max()),
        "mean": float(frame["pIC50"].mean()),
        "median": float(frame["pIC50"].median()),
    }
    statistics_path.write_text(json.dumps(statistics, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"dataset": str(dataset_path), "statistics": str(statistics_path), **statistics}, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    targets = commands.add_parser("targets", help="List ChEMBL target candidates for a query.")
    targets.add_argument("--target", required=True, help="Target name, gene symbol, or protein name.")
    dataset = commands.add_parser("dataset", help="Build the IC50/pIC50 dataset for a confirmed ChEMBL target.")
    dataset.add_argument("--target-id", required=True, help="Confirmed ChEMBL target ID, for example CHEMBL203.")
    dataset.add_argument("--output-dir", required=True, type=Path, help="Directory for dataset.csv and statistics.json.")
    dataset.add_argument("--overwrite", action="store_true", help="Allow replacing existing output files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "targets":
            list_targets(args.target)
        else:
            build_dataset(args.target_id, args.output_dir, args.overwrite)
    except (FileExistsError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
