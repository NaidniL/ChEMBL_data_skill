#!/usr/bin/env python3
"""Independently validate M2–M5 artifacts listed in a run manifest."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from rdkit import Chem, DataStructs


RAW_COLUMNS = {
    "activity_id", "molecule_chembl_id", "target_chembl_id", "assay_chembl_id", "standard_type",
    "standard_relation", "standard_value", "standard_units", "pchembl_value", "data_validity_comment",
    "potential_duplicate",
}
ANALYSIS_COLUMNS = {
    "activity_id", "molecule_chembl_id", "standard_type", "standard_relation", "standard_value", "standard_units",
    "data_validity_comment", "ic50_nM", "pIC50",
}
EXCLUDED_VALIDITY_COMMENT = "Outside typical range"
VALIDITY_POLICY = {
    "accepted": None,
    "excluded": [EXCLUDED_VALIDITY_COMMENT],
    "unknown_non_null": "fail / report for review",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-manifest-json", required=True, type=Path, help="M5 run_manifest.json file.")
    parser.add_argument("--report-json", type=Path, help="Optional path for the readable validation report.")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacement of an existing validation report.")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def add_error(errors: list[dict[str, str]], check: str, artifact: str, message: str, remediation: str) -> None:
    errors.append({"check": check, "artifact": artifact, "message": message, "remediation": remediation})


def read_csv(artifacts: dict[str, str], key: str, errors: list[dict[str, str]]) -> pd.DataFrame | None:
    path = Path(artifacts.get(key, ""))
    if not path.is_file():
        add_error(errors, "artifact_exists", key, f"Artifact is missing: {path}", "Recreate the stage output and rebuild the manifest.")
        return None
    try:
        return pd.read_csv(path)
    except Exception as exc:
        add_error(errors, "csv_readable", key, f"Could not read CSV: {exc}", "Regenerate this CSV from its producing stage.")
        return None


def close(actual: float, expected: float) -> bool:
    return math.isclose(float(actual), float(expected), rel_tol=1e-9, abs_tol=1e-9)


def expected_statistics(series: pd.Series) -> dict[str, float | int | None]:
    values = pd.to_numeric(series, errors="coerce").dropna()

    def optional(value: float) -> float | None:
        return None if pd.isna(value) else float(value)

    return {
        "count": int(len(values)),
        "mean": optional(values.mean()),
        "median": optional(values.median()),
        "standard_deviation": optional(values.std()),
        "minimum": optional(values.min()),
        "q1": optional(values.quantile(0.25)),
        "q3": optional(values.quantile(0.75)),
        "maximum": optional(values.max()),
    }


def validate_run(manifest_path: Path) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    try:
        manifest = load_json(manifest_path)
    except Exception as exc:
        return {
            "valid": False,
            "message": "Validation could not start because the run manifest is unreadable.",
            "errors": [{"check": "manifest_readable", "artifact": str(manifest_path), "message": str(exc), "remediation": "Rebuild run_manifest.json."}],
        }

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return {
            "valid": False,
            "message": "Validation could not start because artifacts are absent from the manifest.",
            "errors": [{"check": "manifest_schema", "artifact": str(manifest_path), "message": "Missing artifacts object.", "remediation": "Rebuild run_manifest.json."}],
        }

    raw = read_csv(artifacts, "raw_activities_csv", errors)
    cleaned = read_csv(artifacts, "cleaned_activities_csv", errors)
    structures = read_csv(artifacts, "structures_csv", errors)
    prepared = read_csv(artifacts, "prepared_csv", errors)
    analyzed = read_csv(artifacts, "analyzed_csv", errors)
    top_records = read_csv(artifacts, "top_records_csv", errors)
    bottom_records = read_csv(artifacts, "bottom_records_csv", errors)

    metadata: dict[str, dict[str, Any]] = {}
    for artifact_key in ("raw_metadata_json", "preparation_metadata_json", "statistics_json", "exclusions_json"):
        path = Path(artifacts.get(artifact_key, ""))
        try:
            metadata[artifact_key] = load_json(path)
        except Exception as exc:
            add_error(errors, "json_readable", artifact_key, f"Could not read JSON: {exc}", "Regenerate this JSON artifact.")

    if raw is not None:
        missing = sorted(RAW_COLUMNS.difference(raw.columns))
        if missing:
            add_error(errors, "raw_schema", "raw_activities_csv", f"Missing raw columns: {', '.join(missing)}.", "Use M2 activities.csv without changing its schema.")
        if "raw_metadata_json" in metadata and len(raw) != metadata["raw_metadata_json"].get("record_count"):
            add_error(errors, "raw_record_count", "raw_activities_csv", "Raw CSV row count differs from M2 metadata.", "Regenerate M2 artifacts together.")

    if cleaned is not None:
        required = manifest.get("configuration", {}).get("base_preparation", {}).get("activity_cleaning", {}).get("required_columns", [])
        if not isinstance(required, list) or not required:
            add_error(errors, "preparation_configuration", "run_manifest_json", "M3 required-column configuration is missing.", "Rebuild M3 artifacts and the manifest.")
        else:
            missing = sorted(set(required).difference(cleaned.columns))
            if missing:
                add_error(errors, "cleaned_schema", "cleaned_activities_csv", f"Missing required cleaned columns: {', '.join(missing)}.", "Regenerate M3 cleaned activities.")
            elif cleaned.loc[:, required].isna().any().any():
                add_error(errors, "cleaned_required_values", "cleaned_activities_csv", "Required cleaned activity fields contain missing values.", "Re-run M3 cleaning from the raw artifact.")
        if cleaned.duplicated().any():
            add_error(errors, "exact_duplicates", "cleaned_activities_csv", "Exact duplicate activity rows remain after M3.", "Re-run M3 cleaning.")

    if "preparation_metadata_json" in metadata:
        preparation = metadata["preparation_metadata_json"]
        expected_counts = {
            "raw_activity_rows": len(raw) if raw is not None else None,
            "cleaned_activity_rows": len(cleaned) if cleaned is not None else None,
            "activity_rows_before_merge": len(cleaned) if cleaned is not None else None,
            "activity_rows_after_merge": len(prepared) if prepared is not None else None,
            "structure_records_retrieved": len(structures) if structures is not None else None,
        }
        for key, expected in expected_counts.items():
            if expected is not None and preparation.get(key) != expected:
                add_error(errors, "preparation_metadata_count", "preparation_metadata_json", f"{key} differs from its artifact row count.", "Regenerate M3 artifacts together.")

    if structures is not None:
        required_structure_columns = {"molecule_chembl_id", "canonical_smiles", "structure_status"}
        missing = sorted(required_structure_columns.difference(structures.columns))
        if missing:
            add_error(errors, "structure_schema", "structures_csv", f"Missing structure columns: {', '.join(missing)}.", "Regenerate M3 structure output.")
        else:
            if structures["molecule_chembl_id"].duplicated().any():
                add_error(errors, "structure_keys", "structures_csv", "Structure table has duplicate molecule_chembl_id values.", "Regenerate M3 structure output.")
            for index, row in structures.iterrows():
                status = row["structure_status"]
                smiles = row["canonical_smiles"]
                parsed = Chem.MolFromSmiles(smiles) if isinstance(smiles, str) and smiles else None
                if status == "valid" and parsed is None:
                    add_error(errors, "valid_smiles", "structures_csv", f"Row {index} is marked valid but its SMILES is not parseable.", "Correct the structure status or regenerate M3 structures.")
                if status == "missing_smiles" and isinstance(smiles, str) and smiles:
                    add_error(errors, "missing_smiles_status", "structures_csv", f"Row {index} is marked missing_smiles but contains a SMILES value.", "Regenerate M3 structures.")
                if status == "invalid_smiles" and parsed is not None:
                    add_error(errors, "invalid_smiles_status", "structures_csv", f"Row {index} is marked invalid_smiles but parses successfully.", "Regenerate M3 structures.")

    fingerprint_length = manifest.get("configuration", {}).get("base_preparation", {}).get("fingerprint", {}).get("length")
    if not isinstance(fingerprint_length, int):
        add_error(errors, "fingerprint_configuration", "run_manifest_json", "Fingerprint length configuration is missing.", "Rebuild M3 artifacts and the manifest.")
    if prepared is not None:
        required_prepared = {"molecule_chembl_id", "canonical_smiles", "structure_status", "fingerprint", "data_validity_comment"}
        missing = sorted(required_prepared.difference(prepared.columns))
        if missing:
            add_error(errors, "prepared_schema", "prepared_csv", f"Missing prepared columns: {', '.join(missing)}.", "Regenerate M3 prepared dataset.")
        else:
            if not prepared["structure_status"].eq("valid").all():
                add_error(errors, "prepared_structure_status", "prepared_csv", "Prepared data contains a non-valid structure status.", "Only valid structures may enter M3 prepared data.")
            if prepared["molecule_chembl_id"].isna().any() or prepared["molecule_chembl_id"].astype("string").str.strip().eq("").any():
                add_error(errors, "prepared_molecule_ids", "prepared_csv", "Prepared data contains a missing molecule_chembl_id.", "Regenerate M3 prepared data.")
            unknown_comments = prepared["data_validity_comment"].notna() & ~prepared["data_validity_comment"].astype("string").str.strip().eq(EXCLUDED_VALIDITY_COMMENT)
            if unknown_comments.any():
                add_error(errors, "unknown_validity_comment", "prepared_csv", "Prepared data contains unknown non-null data_validity_comment values.", "Review the affected records; M4 must fail until the validity policy is explicitly extended.")
            for index, row in prepared.iterrows():
                if Chem.MolFromSmiles(row["canonical_smiles"]) is None:
                    add_error(errors, "prepared_smiles", "prepared_csv", f"Row {index} has an unparseable prepared SMILES.", "Regenerate M3 prepared data.")
                    break
                fingerprint = row["fingerprint"]
                bits = fingerprint.removeprefix("bitstring:") if isinstance(fingerprint, str) else ""
                if not isinstance(fingerprint, str) or not fingerprint.startswith("bitstring:") or len(bits) != fingerprint_length or set(bits) - {"0", "1"}:
                    add_error(errors, "fingerprint_encoding", "prepared_csv", f"Row {index} has an invalid fingerprint encoding.", "Regenerate M3 prepared data.")
                    break
                try:
                    DataStructs.CreateFromBitString(bits)
                except Exception as exc:
                    add_error(errors, "fingerprint_parseable", "prepared_csv", f"Row {index} fingerprint cannot be parsed: {exc}", "Regenerate M3 prepared data.")
                    break

    if analyzed is not None:
        missing = sorted(ANALYSIS_COLUMNS.difference(analyzed.columns))
        if missing:
            add_error(errors, "analysis_schema", "analyzed_csv", f"Missing analysis columns: {', '.join(missing)}.", "Regenerate M4 analysis output.")
        else:
            values = pd.to_numeric(analyzed["standard_value"], errors="coerce")
            ic50_nm = pd.to_numeric(analyzed["ic50_nM"], errors="coerce")
            pic50 = pd.to_numeric(analyzed["pIC50"], errors="coerce")
            if not analyzed["standard_relation"].eq("=").all():
                add_error(errors, "analysis_relation", "analyzed_csv", "Analyzed data contains a non-exact relation.", "Regenerate M4 analysis output.")
            if analyzed["data_validity_comment"].notna().any():
                add_error(errors, "analysis_validity_comment", "analyzed_csv", "Analyzed data retains a data_validity_comment.", "Regenerate M4 analysis output.")
            if analyzed["molecule_chembl_id"].isna().any() or analyzed["molecule_chembl_id"].astype("string").str.strip().eq("").any():
                add_error(errors, "analysis_molecule_ids", "analyzed_csv", "Analyzed data contains a missing molecule_chembl_id.", "Regenerate M4 analysis output.")
            if not (np.isfinite(values).all() and values.gt(0).all() and np.isfinite(ic50_nm).all() and ic50_nm.gt(0).all() and np.isfinite(pic50).all()):
                add_error(errors, "analysis_quantitative_values", "analyzed_csv", "Analyzed IC50 or pIC50 values are not finite positive quantities.", "Regenerate M4 analysis output.")
            factors = manifest.get("configuration", {}).get("semantic_analysis", {}).get("unit_to_nM_factors", {})
            expected_nm = values * analyzed["standard_units"].map(factors)
            expected_pic50 = 9 - np.log10(ic50_nm)
            if expected_nm.isna().any() or not np.allclose(ic50_nm, expected_nm, rtol=1e-9, atol=1e-9):
                add_error(errors, "unit_normalization", "analyzed_csv", "ic50_nM does not match standard_value and the configured unit factor.", "Regenerate M4 analysis output.")
            if not np.allclose(pic50, expected_pic50, rtol=1e-9, atol=1e-9):
                add_error(errors, "pic50_transformation", "analyzed_csv", "pIC50 does not match 9 - log10(ic50_nM).", "Regenerate M4 analysis output.")

    semantic_filter = manifest.get("configuration", {}).get("semantic_analysis", {}).get("semantic_filter", {})
    if semantic_filter.get("data_validity_comment") != VALIDITY_POLICY:
        add_error(errors, "validity_policy", "run_manifest_json", "Manifest does not record the configured data_validity_comment policy.", "Regenerate M4 and M5 artifacts with the configured validity policy.")

    if analyzed is not None and "statistics_json" in metadata:
        statistics = metadata["statistics_json"]
        if prepared is not None and len(prepared) != statistics.get("input_records"):
            add_error(errors, "analysis_input_count", "statistics_json", "Statistics input_records differs from prepared CSV length.", "Regenerate M4 artifacts together.")
        if len(analyzed) != statistics.get("analyzed_records"):
            add_error(errors, "analysis_record_count", "statistics_json", "Statistics analyzed_records differs from analyzed CSV length.", "Regenerate M4 artifacts together.")
        for metric in ("ic50_nM", "pIC50"):
            reported = statistics.get("statistics", {}).get(metric)
            if not isinstance(reported, dict):
                add_error(errors, "statistics_schema", "statistics_json", f"Missing statistics for {metric}.", "Regenerate M4 statistics.")
                continue
            for key, expected in expected_statistics(analyzed[metric]).items():
                actual = reported.get(key)
                if expected is None:
                    matches = actual is None
                else:
                    matches = isinstance(actual, (int, float)) and close(actual, expected)
                if not matches:
                    add_error(errors, "statistics_correctness", "statistics_json", f"{metric}.{key} is {actual!r}, expected {expected!r}.", "Regenerate M4 statistics from analyzed_dataset.csv.")
                    break

    if analyzed is not None and top_records is not None and bottom_records is not None:
        ranking = manifest.get("configuration", {}).get("semantic_analysis", {}).get("ranking", {})
        count = ranking.get("records_per_output") if isinstance(ranking, dict) else None
        if isinstance(count, int):
            expected_top = analyzed.sort_values(["pIC50", "activity_id"], ascending=[False, True], kind="stable").head(count)
            expected_bottom = analyzed.sort_values(["pIC50", "activity_id"], ascending=[True, True], kind="stable").head(count)
            if top_records.get("activity_id", pd.Series(dtype="object")).astype(str).tolist() != expected_top["activity_id"].astype(str).tolist():
                add_error(errors, "top_ranking", "top_records_csv", "Top records do not match descending pIC50 ranking.", "Regenerate M4 ranking outputs.")
            if bottom_records.get("activity_id", pd.Series(dtype="object")).astype(str).tolist() != expected_bottom["activity_id"].astype(str).tolist():
                add_error(errors, "bottom_ranking", "bottom_records_csv", "Bottom records do not match ascending pIC50 ranking.", "Regenerate M4 ranking outputs.")

    record_counts = manifest.get("record_counts", {})
    actual_counts = {
        "raw": len(raw) if raw is not None else None,
        "cleaned": len(cleaned) if cleaned is not None else None,
        "prepared": len(prepared) if prepared is not None else None,
        "analyzed": len(analyzed) if analyzed is not None else None,
    }
    for key, actual in actual_counts.items():
        if actual is not None and record_counts.get(key) != actual:
            add_error(errors, "manifest_record_count", "run_manifest_json", f"Manifest {key} count differs from its CSV length.", "Rebuild run_manifest.json from unchanged artifacts.")
    actual_unique_molecules = {
        "raw": int(raw["molecule_chembl_id"].nunique()) if raw is not None and "molecule_chembl_id" in raw else None,
        "cleaned": int(cleaned["molecule_chembl_id"].nunique()) if cleaned is not None and "molecule_chembl_id" in cleaned else None,
        "prepared": int(prepared["molecule_chembl_id"].nunique()) if prepared is not None and "molecule_chembl_id" in prepared else None,
        "analyzed": int(analyzed["molecule_chembl_id"].nunique()) if analyzed is not None and "molecule_chembl_id" in analyzed else None,
    }
    manifest_unique_molecules = record_counts.get("unique_molecules", {})
    for key, actual in actual_unique_molecules.items():
        if actual is not None and manifest_unique_molecules.get(key) != actual:
            add_error(errors, "manifest_unique_molecules", "run_manifest_json", f"Manifest {key} unique molecule count differs from its CSV.", "Rebuild run_manifest.json from unchanged artifacts.")

    if "exclusions_json" in metadata:
        flow = metadata["exclusions_json"].get("records")
        if not isinstance(flow, list) or not flow:
            add_error(errors, "exclusion_schema", "exclusions_json", "Exclusion flow is missing or empty.", "Rebuild exclusions.json.")
        else:
            previous_output: int | None = None
            for stage in flow:
                if not isinstance(stage, dict):
                    add_error(errors, "exclusion_schema", "exclusions_json", "Exclusion flow has a non-object stage.", "Rebuild exclusions.json.")
                    break
                input_records = stage.get("input_records")
                excluded = stage.get("newly_excluded_records")
                output = stage.get("output_records")
                if not all(isinstance(value, int) and value >= 0 for value in (input_records, excluded, output)) or input_records - excluded != output or (previous_output is not None and input_records != previous_output):
                    add_error(errors, "exclusion_reconciliation", "exclusions_json", f"Invalid count transition at {stage.get('stage')!r}.", "Rebuild exclusions.json from stage metadata.")
                    break
                previous_output = output
            if previous_output is not None and analyzed is not None and previous_output != len(analyzed):
                add_error(errors, "exclusion_final_count", "exclusions_json", "Final exclusion count differs from analyzed CSV length.", "Rebuild exclusions.json.")

    summary = {key: value for key, value in actual_counts.items() if value is not None}
    valid = not errors
    return {
        "valid": valid,
        "message": (
            f"Validation passed: raw={summary.get('raw')}, cleaned={summary.get('cleaned')}, prepared={summary.get('prepared')}, analyzed={summary.get('analyzed')}."
            if valid
            else f"Validation failed with {len(errors)} issue(s). Each issue identifies the artifact and a corrective action."
        ),
        "summary": summary,
        "errors": errors,
    }


def main() -> int:
    args = parse_args()
    if args.report_json and args.report_json.exists() and not args.overwrite:
        print(f"error: refusing to overwrite {args.report_json}. Re-run with --overwrite.", file=sys.stderr)
        return 2
    report = validate_run(args.run_manifest_json)
    if args.report_json:
        args.report_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
