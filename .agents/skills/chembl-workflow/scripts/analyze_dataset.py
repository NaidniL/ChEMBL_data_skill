#!/usr/bin/env python3
"""Normalize exact IC50 values, calculate pIC50, and write statistics and rankings."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = (
    "activity_id",
    "molecule_chembl_id",
    "standard_type",
    "standard_relation",
    "standard_value",
    "standard_units",
    "data_validity_comment",
)
UNIT_TO_NM = {
    "pM": 0.001,
    "nM": 1.0,
    "uM": 1_000.0,
    "µM": 1_000.0,
    "μM": 1_000.0,
    "mM": 1_000_000.0,
}
EXCLUDED_VALIDITY_COMMENT = "Outside typical range"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared-csv", required=True, type=Path, help="M3 prepared_dataset.csv file.")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory for M4 artifacts.")
    parser.add_argument("--activity-type", default="IC50", help="Activity type to analyze; M4 supports IC50 only.")
    parser.add_argument("--top-n", default=10, type=int, help="Number of records in each ranking output.")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacement of existing M4 artifacts.")
    args = parser.parse_args()
    args.activity_type = args.activity_type.strip().upper()
    if args.activity_type != "IC50":
        parser.error("M4 currently supports --activity-type IC50 only")
    if args.top_n < 1:
        parser.error("--top-n must be a positive integer")
    return args


def metric_statistics(series: pd.Series) -> dict[str, int | float | None]:
    values = pd.to_numeric(series, errors="raise").dropna()

    def number(value: float) -> float | None:
        return None if pd.isna(value) else float(value)

    return {
        "count": int(len(values)),
        "mean": number(values.mean()),
        "median": number(values.median()),
        "standard_deviation": number(values.std()),
        "minimum": number(values.min()),
        "q1": number(values.quantile(0.25)),
        "q3": number(values.quantile(0.75)),
        "maximum": number(values.max()),
    }


def analyze_ic50(frame: pd.DataFrame, activity_type: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    dataset = frame.copy()
    dataset.columns = [str(column).strip().lower().replace(" ", "_") for column in dataset.columns]
    if dataset.columns.duplicated().any():
        raise ValueError("Prepared input contains duplicate column names after normalization.")
    missing_columns = sorted(set(REQUIRED_COLUMNS).difference(dataset.columns))
    if missing_columns:
        raise ValueError(f"Prepared input lacks required columns: {', '.join(missing_columns)}")

    for column in ("standard_type", "standard_relation", "standard_units", "data_validity_comment"):
        dataset[column] = dataset[column].astype("string").str.strip().replace("", pd.NA)

    raw_standard_value = dataset["standard_value"]
    numeric_standard_value = pd.to_numeric(raw_standard_value, errors="coerce")
    finite_standard_value = numeric_standard_value.notna() & np.isfinite(numeric_standard_value)
    missing_standard_value = raw_standard_value.isna()
    invalid_standard_value = ~missing_standard_value & ~finite_standard_value
    non_positive_standard_value = finite_standard_value & numeric_standard_value.le(0)

    selected_type = dataset["standard_type"].eq(activity_type)
    exact_relation = dataset["standard_relation"].eq("=")
    unknown_validity_comments = (dataset["data_validity_comment"].notna() & ~dataset["data_validity_comment"].eq(EXCLUDED_VALIDITY_COMMENT)).fillna(False)
    if unknown_validity_comments.any():
        unknown_values = sorted(dataset.loc[unknown_validity_comments, "data_validity_comment"].unique())
        unknown_activity_ids = dataset.loc[unknown_validity_comments, "activity_id"].tolist()
        raise ValueError(
            "Unknown data_validity_comment values require review: "
            f"{unknown_values!r} (activity_id={unknown_activity_ids!r})."
        )
    outside_typical_range = dataset["data_validity_comment"].eq(EXCLUDED_VALIDITY_COMMENT).fillna(False)
    supported_unit = dataset["standard_units"].isin(UNIT_TO_NM)
    remaining = pd.Series(True, index=dataset.index)
    wrong_activity_type = remaining & ~selected_type
    remaining &= selected_type
    non_exact_relation = remaining & ~exact_relation
    remaining &= exact_relation
    excluded_validity_comment = remaining & outside_typical_range
    remaining &= ~outside_typical_range
    missing_value = remaining & missing_standard_value
    remaining &= ~missing_standard_value
    invalid_value = remaining & invalid_standard_value
    remaining &= ~invalid_standard_value
    non_positive_value = remaining & non_positive_standard_value
    remaining &= ~non_positive_standard_value
    unsupported_unit = remaining & ~supported_unit
    eligible = remaining & supported_unit
    analyzed = dataset.loc[eligible].copy()
    analyzed["ic50_nM"] = numeric_standard_value.loc[eligible] * analyzed["standard_units"].map(UNIT_TO_NM)
    analyzed["pIC50"] = 9 - np.log10(analyzed["ic50_nM"])
    if not np.isfinite(analyzed["pIC50"]).all():
        raise ValueError("Calculated pIC50 contains non-finite values.")
    analyzed = analyzed.reset_index(drop=True)

    exclusions = {
        "wrong_activity_type": int(wrong_activity_type.sum()),
        "non_exact_relation": int(non_exact_relation.sum()),
        "outside_typical_range": int(excluded_validity_comment.sum()),
        "missing_standard_value": int(missing_value.sum()),
        "invalid_standard_value": int(invalid_value.sum()),
        "non_positive_standard_value": int(non_positive_value.sum()),
        "unsupported_or_missing_unit": int(unsupported_unit.sum()),
    }
    metadata = {
        "input_records": int(len(dataset)),
        "activity_type": activity_type,
        "exact_relation_required": "=",
        "canonical_ic50_unit": "nM",
        "unit_to_nM_factors": UNIT_TO_NM,
        "semantic_filter": {
            "activity_type": activity_type,
            "standard_relation": "=",
            "data_validity_comment": {
                "accepted": None,
                "excluded": [EXCLUDED_VALIDITY_COMMENT],
                "unknown_non_null": "fail / report for review",
            },
            "standard_value": "finite and greater than zero",
            "supported_units": list(UNIT_TO_NM),
        },
        "transformation": "pIC50 = 9 - log10(ic50_nM)",
        "exclusions": exclusions,
        "analyzed_records": int(len(analyzed)),
        "unique_molecules": int(analyzed["molecule_chembl_id"].nunique()),
        "statistics": {
            "ic50_nM": metric_statistics(analyzed["ic50_nM"]),
            "pIC50": metric_statistics(analyzed["pIC50"]),
        },
    }
    return analyzed, metadata


def write_analysis(
    prepared_csv: Path,
    output_dir: Path,
    activity_type: str,
    top_n: int,
    overwrite: bool,
) -> dict[str, Any]:
    artifacts = {
        "analyzed_dataset_csv": output_dir / "analyzed_dataset.csv",
        "statistics_json": output_dir / "statistics.json",
        "top_records_csv": output_dir / "top_records.csv",
        "bottom_records_csv": output_dir / "bottom_records.csv",
    }
    existing = [path for path in artifacts.values() if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(f"Refusing to overwrite {', '.join(str(path) for path in existing)}. Re-run with --overwrite.")

    analyzed, metadata = analyze_ic50(pd.read_csv(prepared_csv), activity_type)
    if analyzed.empty:
        raise ValueError("No exact, positive IC50 records with supported units are available for analysis.")
    top_records = analyzed.sort_values(["pIC50", "activity_id"], ascending=[False, True], kind="stable").head(top_n)
    bottom_records = analyzed.sort_values(["pIC50", "activity_id"], ascending=[True, True], kind="stable").head(top_n)
    metadata["ranking"] = {
        "metric": "pIC50",
        "top_order": "descending; higher pIC50 indicates stronger activity",
        "bottom_order": "ascending; lower pIC50 indicates weaker activity",
        "records_per_output": top_n,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    analyzed.to_csv(artifacts["analyzed_dataset_csv"], index=False)
    top_records.to_csv(artifacts["top_records_csv"], index=False)
    bottom_records.to_csv(artifacts["bottom_records_csv"], index=False)
    artifacts["statistics_json"].write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return {name: str(path) for name, path in artifacts.items()} | metadata


def main() -> int:
    args = parse_args()
    try:
        print(json.dumps(write_analysis(**vars(args)), indent=2))
    except Exception as exc:
        print(f"error: dataset analysis failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
