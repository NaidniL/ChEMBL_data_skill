#!/usr/bin/env python3
"""Fetch and preserve raw ChEMBL activity records for a resolved target."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
from requests.exceptions import RequestException


RAW_ACTIVITY_COLUMNS = (
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
CHEMBL_TARGET_ID = re.compile(r"^CHEMBL\d+$")
new_client: Any | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-chembl-id", required=True, help="Resolved ChEMBL target ID, for example CHEMBL203.")
    parser.add_argument("--activity-type", required=True, help="Requested ChEMBL standard activity type, for example IC50.")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory for activities.csv and metadata.json.")
    parser.add_argument("--limit", type=int, help="Optional maximum number of raw records to retrieve from ChEMBL.")
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help="Enable the ChEMBL client cache. Disabled by default to avoid stale activity responses.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Allow replacement of existing output files.")
    args = parser.parse_args()
    if not CHEMBL_TARGET_ID.fullmatch(args.target_chembl_id):
        parser.error("--target-chembl-id must match CHEMBL followed by digits")
    if not args.activity_type.strip():
        parser.error("--activity-type must not be empty")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be a positive integer")
    return args


def fetch_records(
    target_chembl_id: str,
    activity_type: str,
    limit: int | None = None,
    use_cache: bool = False,
) -> list[dict[str, Any]]:
    global new_client
    if new_client is None:
        for attempt in range(2):
            try:
                from chembl_webresource_client.settings import Settings

                Settings.Instance().CACHING = use_cache
                from chembl_webresource_client.new_client import new_client as chembl_client

                new_client = chembl_client
                break
            except (OSError, RequestException) as exc:
                if attempt == 1:
                    raise RuntimeError("ChEMBL client initialization failed after 2 attempts.") from exc
                time.sleep(1)

    for attempt in range(2):
        try:
            query = new_client.activity.filter(
                target_chembl_id=target_chembl_id,
                standard_type=activity_type,
            )
            records_query = query.only(*RAW_ACTIVITY_COLUMNS)
            if limit is not None:
                records_query = records_query[:limit]
            records = list(records_query)
        except RequestException as exc:
            if attempt == 1:
                raise RuntimeError("ChEMBL activity request failed after 2 attempts.") from exc
            time.sleep(1)
            continue
        if not records:
            raise ValueError(f"No {activity_type} activity records were returned for {target_chembl_id}.")
        return records

    raise RuntimeError("ChEMBL activity request ended without a response.")


def validate_raw_frame(frame: pd.DataFrame, target_chembl_id: str, activity_type: str) -> None:
    missing_columns = sorted(set(RAW_ACTIVITY_COLUMNS).difference(frame.columns))
    if missing_columns:
        raise ValueError(f"ChEMBL activity response lacks required fields: {', '.join(missing_columns)}")
    if not frame["target_chembl_id"].eq(target_chembl_id).all():
        raise ValueError("ChEMBL activity response contains a target_chembl_id different from the requested target.")
    if not frame["standard_type"].eq(activity_type).all():
        raise ValueError("ChEMBL activity response contains a standard_type different from the requested activity type.")


def save_raw_dataset(
    target_chembl_id: str,
    activity_type: str,
    output_dir: Path,
    overwrite: bool,
    limit: int | None = None,
    use_cache: bool = False,
) -> dict[str, Any]:
    csv_path = output_dir / "activities.csv"
    metadata_path = output_dir / "metadata.json"
    existing = [path for path in (csv_path, metadata_path) if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(f"Refusing to overwrite {', '.join(str(path) for path in existing)}. Re-run with --overwrite.")

    frame = pd.DataFrame(fetch_records(target_chembl_id, activity_type, limit, use_cache))
    validate_raw_frame(frame, target_chembl_id, activity_type)
    raw_frame = frame.loc[:, list(RAW_ACTIVITY_COLUMNS)]
    metadata = {
        "target_chembl_id": target_chembl_id,
        "activity_type": activity_type,
        "record_count": int(len(raw_frame)),
        "columns": list(RAW_ACTIVITY_COLUMNS),
        "client_cache_enabled": use_cache,
        "cache_policy": "disabled by default; enable only with --use-cache",
    }
    if limit is not None:
        metadata["query_limit"] = limit
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_frame.to_csv(csv_path, index=False)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return {"activities_csv": str(csv_path), "metadata_json": str(metadata_path), **metadata}


def main() -> int:
    args = parse_args()
    try:
        print(json.dumps(save_raw_dataset(**vars(args)), indent=2))
    except Exception as exc:
        print(f"error: ChEMBL activity query failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
