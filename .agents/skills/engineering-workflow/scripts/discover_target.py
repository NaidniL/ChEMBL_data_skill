#!/usr/bin/env python3
"""Fetch ChEMBL target candidates without local filtering or transformation.

Accept exactly one identifier: a target name, UniProt accession, or ChEMBL
target ID. The optional organism is forwarded to ChEMBL as a query constraint.
The JSON output always has a ``candidates`` list and contains zero or more
records returned by ChEMBL. This script does not sort, deduplicate, remove, or
alter candidates.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

CANDIDATE_FIELDS = ("target_chembl_id", "organism", "pref_name", "target_type")
UNIPROT_ACCESSION = re.compile(r"^[A-Z0-9]{6,10}$")
CHEMBL_TARGET_ID = re.compile(r"^CHEMBL\d+$")
# Extend this mapping together with a new mutually exclusive CLI argument when
# adding a ChEMBL discovery interface. Keep every interface on the same output
# contract and do not introduce local result processing.
QUERY_FIELDS = {
    "target_name": "pref_name",
    "uniprot_accession": "target_components__accession",
    "chembl_target_id": "target_chembl_id",
}
new_client: Any | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    identifiers = parser.add_mutually_exclusive_group(required=True)
    identifiers.add_argument("--target-name", help="Non-empty ChEMBL target preferred name.")
    identifiers.add_argument("--uniprot-accession", help="UniProt accession, for example P00533.")
    identifiers.add_argument("--chembl-target-id", help="ChEMBL target ID, for example CHEMBL203.")
    parser.add_argument("--organism", help="Optional organism forwarded to the ChEMBL target query.")
    args = parser.parse_args()

    if args.target_name is not None and not args.target_name.strip():
        parser.error("--target-name must not be empty")
    if args.uniprot_accession is not None and not UNIPROT_ACCESSION.fullmatch(args.uniprot_accession):
        parser.error("--uniprot-accession must be a 6-10 character uppercase UniProt accession")
    if args.chembl_target_id is not None and not CHEMBL_TARGET_ID.fullmatch(args.chembl_target_id):
        parser.error("--chembl-target-id must match CHEMBL followed by digits")
    if args.organism is not None and not args.organism.strip():
        parser.error("--organism must not be empty")
    return args


def target_query(args: argparse.Namespace) -> tuple[str, str, dict[str, str]]:
    identifier_type, value = next(
        (name, getattr(args, name)) for name in QUERY_FIELDS if getattr(args, name) is not None
    )
    query = {QUERY_FIELDS[identifier_type]: value}
    if args.organism is not None:
        query["organism"] = args.organism
    return identifier_type, value, query


def discover_targets(args: argparse.Namespace) -> dict[str, Any]:
    global new_client
    if new_client is None:
        from chembl_webresource_client.new_client import new_client as chembl_client

        new_client = chembl_client
    identifier_type, value, query = target_query(args)
    candidates = list(new_client.target.get(**query).only(*CANDIDATE_FIELDS))
    return {
        "query": {
            "identifier_type": identifier_type,
            "value": value,
            "organism": args.organism,
        },
        "candidates": candidates,
    }


def main() -> int:
    args = parse_args()
    try:
        print(json.dumps(discover_targets(args), ensure_ascii=False, indent=2))
    except Exception as exc:
        print(f"error: ChEMBL target query failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
