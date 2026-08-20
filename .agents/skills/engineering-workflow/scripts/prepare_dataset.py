#!/usr/bin/env python3
"""Clean raw activities, retrieve ChEMBL structures, and build a fingerprinted dataset."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
from rdkit import Chem
from rdkit.Chem import rdFingerprintGenerator
from requests.exceptions import RequestException


ACTIVITY_COLUMNS = (
    "activity_id",
    "molecule_chembl_id",
    "target_chembl_id",
    "assay_chembl_id",
    "standard_type",
    "standard_relation",
    "standard_value",
    "standard_units",
    "pchembl_value",
    "data_validity_comment",
    "potential_duplicate",
)
REQUIRED_ACTIVITY_COLUMNS = (
    "activity_id",
    "molecule_chembl_id",
    "standard_type",
    "standard_relation",
    "standard_value",
    "standard_units",
)
STRING_ACTIVITY_COLUMNS = (
    "molecule_chembl_id",
    "target_chembl_id",
    "assay_chembl_id",
    "standard_type",
    "standard_relation",
    "standard_units",
    "data_validity_comment",
)
FINGERPRINT_RADIUS = 2
FINGERPRINT_LENGTH = 2048
new_client: Any | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--activities-csv", required=True, type=Path, help="M2 activities.csv file.")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory for M3 artifacts.")
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help="Enable the ChEMBL client cache. Disabled by default to avoid stale structure responses.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Allow replacement of existing M3 artifacts.")
    return parser.parse_args()


def clean_activities(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    activities = frame.copy()
    activities.columns = [str(column).strip().lower().replace(" ", "_") for column in activities.columns]
    if activities.columns.duplicated().any():
        raise ValueError("Activity input contains duplicate column names after normalization.")

    missing_columns = sorted(set(ACTIVITY_COLUMNS).difference(activities.columns))
    if missing_columns:
        raise ValueError(f"Activity input lacks required M2 columns: {', '.join(missing_columns)}")
    activities = activities.loc[:, list(ACTIVITY_COLUMNS)]

    for column in STRING_ACTIVITY_COLUMNS:
        activities[column] = activities[column].astype("string").str.strip().replace("", pd.NA)

    raw_activity_id = activities["activity_id"]
    raw_standard_value = activities["standard_value"]
    raw_pchembl_value = activities["pchembl_value"]
    raw_potential_duplicate = activities["potential_duplicate"]
    activities["activity_id"] = pd.to_numeric(raw_activity_id, errors="coerce").astype("Int64")
    activities["standard_value"] = pd.to_numeric(raw_standard_value, errors="coerce").astype("Float64")
    activities["pchembl_value"] = pd.to_numeric(raw_pchembl_value, errors="coerce").astype("Float64")
    activities["potential_duplicate"] = pd.to_numeric(raw_potential_duplicate, errors="coerce").astype("Int64")

    numeric_conversion_failures = {
        "activity_id": int(raw_activity_id.notna().sum() - activities["activity_id"].notna().sum()),
        "standard_value": int(raw_standard_value.notna().sum() - activities["standard_value"].notna().sum()),
        "pchembl_value": int(raw_pchembl_value.notna().sum() - activities["pchembl_value"].notna().sum()),
        "potential_duplicate": int(
            raw_potential_duplicate.notna().sum() - activities["potential_duplicate"].notna().sum()
        ),
    }
    required_missing = activities.loc[:, list(REQUIRED_ACTIVITY_COLUMNS)].isna().any(axis=1)
    cleaned = activities.loc[~required_missing].copy()
    exact_duplicates = cleaned.duplicated()
    cleaned = cleaned.loc[~exact_duplicates].reset_index(drop=True)

    return cleaned, {
        "raw_activity_rows": int(len(activities)),
        "dropped_missing_required_fields": int(required_missing.sum()),
        "dropped_exact_duplicate_rows": int(exact_duplicates.sum()),
        "numeric_conversion_failures": numeric_conversion_failures,
        "cleaned_activity_rows": int(len(cleaned)),
        "aggregation_strategy": "keep_all",
    }


def fetch_structure_records(molecule_ids: list[str], use_cache: bool) -> list[dict[str, Any]]:
    global new_client
    if new_client is None:
        try:
            from chembl_webresource_client.settings import Settings

            Settings.Instance().CACHING = use_cache
            from chembl_webresource_client.new_client import new_client as chembl_client

            new_client = chembl_client
        except (OSError, RequestException) as exc:
            raise RuntimeError("ChEMBL structure client initialization failed.") from exc

    records = []
    for molecule_chembl_id in molecule_ids:
        for attempt in range(2):
            try:
                records.append(new_client.molecule.get(molecule_chembl_id))
                break
            except (OSError, RequestException) as exc:
                if attempt == 1:
                    raise RuntimeError(f"ChEMBL structure request failed for {molecule_chembl_id} after 2 attempts.") from exc
                time.sleep(1)
    return records


def validate_structures(molecule_ids: list[str], records: list[dict[str, Any]]) -> tuple[pd.DataFrame, dict[str, int]]:
    if len(records) != len(molecule_ids):
        raise ValueError("ChEMBL returned a structure record count different from the requested molecule count.")

    rows = []
    for molecule_chembl_id, record in zip(molecule_ids, records, strict=True):
        if not isinstance(record, dict):
            raise ValueError(f"ChEMBL returned a non-record structure response for {molecule_chembl_id}.")
        if record.get("molecule_chembl_id") != molecule_chembl_id:
            raise ValueError(f"ChEMBL returned a structure record for a different molecule than {molecule_chembl_id}.")
        structures = record.get("molecule_structures") or {}
        canonical_smiles = structures.get("canonical_smiles")
        if not isinstance(canonical_smiles, str) or not canonical_smiles.strip():
            rows.append(
                {
                    "molecule_chembl_id": molecule_chembl_id,
                    "canonical_smiles": pd.NA,
                    "structure_status": "missing_smiles",
                }
            )
            continue
        canonical_smiles = canonical_smiles.strip()
        if Chem.MolFromSmiles(canonical_smiles) is None:
            rows.append(
                {
                    "molecule_chembl_id": molecule_chembl_id,
                    "canonical_smiles": canonical_smiles,
                    "structure_status": "invalid_smiles",
                }
            )
            continue
        rows.append(
            {
                "molecule_chembl_id": molecule_chembl_id,
                "canonical_smiles": canonical_smiles,
                "structure_status": "valid",
            }
        )

    structures = pd.DataFrame(rows, columns=["molecule_chembl_id", "canonical_smiles", "structure_status"])
    if structures["molecule_chembl_id"].duplicated().any():
        raise ValueError("Structure table contains duplicate molecule_chembl_id values.")
    return structures, {
        "structure_records_retrieved": int(len(structures)),
        "valid_structures": int((structures["structure_status"] == "valid").sum()),
        "missing_smiles": int((structures["structure_status"] == "missing_smiles").sum()),
        "invalid_smiles": int((structures["structure_status"] == "invalid_smiles").sum()),
    }


def merge_and_fingerprint(activities: pd.DataFrame, structures: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    valid_structures = structures.loc[structures["structure_status"] == "valid"].copy()
    merged = activities.merge(valid_structures, on="molecule_chembl_id", how="inner", validate="many_to_one", sort=False)
    rows_lost = len(activities) - len(merged)
    if len(merged) + rows_lost != len(activities):
        raise ValueError("Activity-to-structure merge counts do not reconcile.")

    generator = rdFingerprintGenerator.GetMorganGenerator(radius=FINGERPRINT_RADIUS, fpSize=FINGERPRINT_LENGTH)
    fingerprints = []
    for smiles in merged["canonical_smiles"]:
        molecule = Chem.MolFromSmiles(smiles)
        if molecule is None:
            raise ValueError("A structure marked valid could not be parsed while generating fingerprints.")
        fingerprint_bits = generator.GetFingerprint(molecule).ToBitString()
        if len(fingerprint_bits) != FINGERPRINT_LENGTH:
            raise ValueError("Generated fingerprint length differs from the configured length.")
        fingerprints.append(f"bitstring:{fingerprint_bits}")
    merged["fingerprint"] = pd.Series(fingerprints, index=merged.index, dtype="string")
    if not merged["fingerprint"].str.removeprefix("bitstring:").str.len().eq(FINGERPRINT_LENGTH).all():
        raise ValueError("Prepared dataset contains inconsistent fingerprint lengths.")
    merged = merged.reset_index(drop=True)
    return merged, {
        "activity_rows_before_merge": int(len(activities)),
        "activity_rows_after_merge": int(len(merged)),
        "activity_rows_lost_no_valid_structure": int(rows_lost),
    }


def prepare_dataset(activities_csv: Path, output_dir: Path, use_cache: bool, overwrite: bool) -> dict[str, Any]:
    artifacts = {
        "activities_clean_csv": output_dir / "activities_clean.csv",
        "structures_csv": output_dir / "structures.csv",
        "prepared_dataset_csv": output_dir / "prepared_dataset.csv",
        "metadata_json": output_dir / "preparation_metadata.json",
    }
    existing = [path for path in artifacts.values() if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(f"Refusing to overwrite {', '.join(str(path) for path in existing)}. Re-run with --overwrite.")

    cleaned_activities, activity_metadata = clean_activities(pd.read_csv(activities_csv))
    if cleaned_activities.empty:
        raise ValueError("No activity records remain after required-field cleaning.")
    molecule_ids = cleaned_activities["molecule_chembl_id"].drop_duplicates().tolist()
    structures, structure_metadata = validate_structures(molecule_ids, fetch_structure_records(molecule_ids, use_cache))
    prepared, merge_metadata = merge_and_fingerprint(cleaned_activities, structures)
    metadata = {
        **activity_metadata,
        **structure_metadata,
        **merge_metadata,
        "unique_molecules_requested": int(len(molecule_ids)),
        "client_cache_enabled": use_cache,
        "aggregation_strategy": "keep_all",
        "fingerprint": {
            "type": "Morgan",
            "radius": FINGERPRINT_RADIUS,
            "length": FINGERPRINT_LENGTH,
            "storage": "bitstring: prefix followed by a 2048-character bitstring in prepared_dataset.csv",
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    cleaned_activities.to_csv(artifacts["activities_clean_csv"], index=False)
    structures.to_csv(artifacts["structures_csv"], index=False)
    prepared.to_csv(artifacts["prepared_dataset_csv"], index=False)
    artifacts["metadata_json"].write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return {name: str(path) for name, path in artifacts.items()} | metadata


def main() -> int:
    args = parse_args()
    try:
        print(json.dumps(prepare_dataset(**vars(args)), indent=2))
    except Exception as exc:
        print(f"error: dataset preparation failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
