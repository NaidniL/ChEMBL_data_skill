#!/usr/bin/env python3
"""Build verifiable run_manifest.json and exclusions.json from M2–M4 artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from csv import DictReader
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any


SEMANTIC_EXCLUSION_ORDER = (
    "wrong_activity_type",
    "non_exact_relation",
    "outside_typical_range",
    "missing_standard_value",
    "invalid_standard_value",
    "non_positive_standard_value",
    "unsupported_or_missing_unit",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    for option, help_text in (
        ("raw-activities-csv", "M2 activities.csv"),
        ("raw-metadata-json", "M2 metadata.json"),
        ("cleaned-activities-csv", "M3 activities_clean.csv"),
        ("structures-csv", "M3 structures.csv"),
        ("preparation-metadata-json", "M3 preparation_metadata.json"),
        ("prepared-csv", "M3 prepared_dataset.csv"),
        ("analyzed-csv", "M4 analyzed_dataset.csv"),
        ("statistics-json", "M4 statistics.json"),
        ("top-records-csv", "M4 top_records.csv"),
        ("bottom-records-csv", "M4 bottom_records.csv"),
    ):
        parser.add_argument(f"--{option}", required=True, type=Path, help=help_text)
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory for M5 JSON artifacts.")
    parser.add_argument("--original-target-query", required=True, help="Actual target query supplied for this run.")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacement of existing M5 JSON artifacts.")
    args = parser.parse_args()
    if not args.original_target_query.strip():
        parser.error("--original-target-query must not be empty")
    return args


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def require_count(metadata: dict[str, Any], key: str, source: str) -> int:
    value = metadata.get(key)
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"{source} has no non-negative integer {key}.")
    return value


def unique_molecule_count(path: Path) -> int:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = DictReader(handle)
        if not reader.fieldnames or "molecule_chembl_id" not in reader.fieldnames:
            raise ValueError(f"{path} lacks molecule_chembl_id for manifest counting.")
        return len({row["molecule_chembl_id"] for row in reader if row["molecule_chembl_id"]})


def build_exclusions(raw_metadata: dict[str, Any], preparation_metadata: dict[str, Any], statistics: dict[str, Any]) -> dict[str, Any]:
    raw_records = require_count(raw_metadata, "record_count", "M2 metadata")
    missing_required = require_count(preparation_metadata, "dropped_missing_required_fields", "M3 metadata")
    exact_duplicates = require_count(preparation_metadata, "dropped_exact_duplicate_rows", "M3 metadata")
    cleaned_records = require_count(preparation_metadata, "cleaned_activity_rows", "M3 metadata")
    merge_input = require_count(preparation_metadata, "activity_rows_before_merge", "M3 metadata")
    merge_loss = require_count(preparation_metadata, "activity_rows_lost_no_valid_structure", "M3 metadata")
    prepared_records = require_count(preparation_metadata, "activity_rows_after_merge", "M3 metadata")
    analysis_input = require_count(statistics, "input_records", "M4 statistics")
    analyzed_records = require_count(statistics, "analyzed_records", "M4 statistics")
    exclusions = statistics.get("exclusions")
    if not isinstance(exclusions, dict):
        raise ValueError("M4 statistics has no exclusions object.")

    if raw_records - missing_required - exact_duplicates != cleaned_records:
        raise ValueError("M3 cleaning counts do not reconcile with M2 raw count.")
    if cleaned_records != merge_input or merge_input - merge_loss != prepared_records:
        raise ValueError("M3 merge counts do not reconcile.")
    if prepared_records != analysis_input:
        raise ValueError("M3 prepared count differs from M4 analysis input count.")

    stages = []
    current = raw_records

    def append_stage(stage: str, reason: str | None, excluded: int) -> None:
        nonlocal current
        if excluded < 0 or excluded > current:
            raise ValueError(f"{stage} exclusion count is incompatible with its input count.")
        output = current - excluded
        stages.append(
            {
                "stage": stage,
                "input_records": current,
                "newly_excluded_records": excluded,
                "reason": reason,
                "output_records": output,
            }
        )
        current = output

    append_stage("M2_raw_acquisition", None, 0)
    append_stage("M3_required_activity_fields", "missing required activity field", missing_required)
    append_stage("M3_exact_duplicates", "exact duplicate activity row", exact_duplicates)
    append_stage("M3_structure_merge", "no valid molecular structure", merge_loss)
    for reason in SEMANTIC_EXCLUSION_ORDER:
        value = exclusions.get(reason)
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"M4 exclusions has no non-negative integer {reason}.")
        append_stage(f"M4_{reason}", reason, value)
    if current != analyzed_records:
        raise ValueError("M4 exclusion counts do not reconcile with analyzed record count.")

    return {
        "schema_version": "1.0",
        "records": stages,
        "structure_quality": {
            "structure_records_retrieved": require_count(preparation_metadata, "structure_records_retrieved", "M3 metadata"),
            "valid_structures": require_count(preparation_metadata, "valid_structures", "M3 metadata"),
            "missing_smiles": require_count(preparation_metadata, "missing_smiles", "M3 metadata"),
            "invalid_smiles": require_count(preparation_metadata, "invalid_smiles", "M3 metadata"),
        },
        "final_analyzed_records": analyzed_records,
    }


def build_manifest(
    raw_activities_csv: Path,
    raw_metadata_json: Path,
    cleaned_activities_csv: Path,
    structures_csv: Path,
    preparation_metadata_json: Path,
    prepared_csv: Path,
    analyzed_csv: Path,
    statistics_json: Path,
    top_records_csv: Path,
    bottom_records_csv: Path,
    output_dir: Path,
    original_target_query: str,
    overwrite: bool,
) -> dict[str, Any]:
    source_paths = {
        "raw_activities_csv": raw_activities_csv,
        "raw_metadata_json": raw_metadata_json,
        "cleaned_activities_csv": cleaned_activities_csv,
        "structures_csv": structures_csv,
        "preparation_metadata_json": preparation_metadata_json,
        "prepared_csv": prepared_csv,
        "analyzed_csv": analyzed_csv,
        "statistics_json": statistics_json,
        "top_records_csv": top_records_csv,
        "bottom_records_csv": bottom_records_csv,
    }
    missing = [str(path) for path in source_paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Required artifact files do not exist: {', '.join(missing)}")
    manifest_path = output_dir / "run_manifest.json"
    exclusions_path = output_dir / "exclusions.json"
    existing = [path for path in (manifest_path, exclusions_path) if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(f"Refusing to overwrite {', '.join(str(path) for path in existing)}. Re-run with --overwrite.")

    raw_metadata = load_json(raw_metadata_json)
    preparation_metadata = load_json(preparation_metadata_json)
    statistics = load_json(statistics_json)
    exclusions = build_exclusions(raw_metadata, preparation_metadata, statistics)
    artifacts = {name: str(path.resolve()) for name, path in source_paths.items()}
    artifacts["exclusions_json"] = str(exclusions_path.resolve())
    manifest = {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "artifacts": artifacts,
        "configuration": {
            "acquisition": {
                "target_chembl_id": raw_metadata.get("target_chembl_id"),
                "original_target_query": original_target_query,
                "activity_type": raw_metadata.get("activity_type"),
                "query_limit": raw_metadata.get("query_limit"),
                "client_cache_enabled": raw_metadata.get("client_cache_enabled"),
                "raw_columns": raw_metadata.get("columns"),
            },
            "base_preparation": {
                "activity_cleaning": preparation_metadata.get("activity_cleaning"),
                "aggregation_strategy": preparation_metadata.get("aggregation_strategy"),
                "structure_validation": preparation_metadata.get("structure_validation"),
                "fingerprint": preparation_metadata.get("fingerprint"),
                "client_cache_enabled": preparation_metadata.get("client_cache_enabled"),
            },
            "semantic_analysis": {
                "semantic_filter": statistics.get("semantic_filter"),
                "canonical_ic50_unit": statistics.get("canonical_ic50_unit"),
                "unit_to_nM_factors": statistics.get("unit_to_nM_factors"),
                "transformation": statistics.get("transformation"),
                "ranking": statistics.get("ranking"),
            },
        },
        "record_counts": {
            "raw": raw_metadata.get("record_count"),
            "cleaned": preparation_metadata.get("cleaned_activity_rows"),
            "prepared": preparation_metadata.get("activity_rows_after_merge"),
            "analyzed": statistics.get("analyzed_records"),
            "unique_molecules": {
                "raw": unique_molecule_count(raw_activities_csv),
                "cleaned": unique_molecule_count(cleaned_activities_csv),
                "prepared": unique_molecule_count(prepared_csv),
                "analyzed": unique_molecule_count(analyzed_csv),
            },
        },
        "software_versions": {
            "chembl_webresource_client": version("chembl_webresource_client"),
            "numpy": version("numpy"),
            "pandas": version("pandas"),
            "rdkit": version("rdkit"),
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    exclusions_path.write_text(json.dumps(exclusions, indent=2) + "\n", encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"run_manifest_json": str(manifest_path), "exclusions_json": str(exclusions_path), **manifest}


def main() -> int:
    args = parse_args()
    try:
        print(json.dumps(build_manifest(**vars(args)), indent=2))
    except Exception as exc:
        print(f"error: run manifest generation failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
