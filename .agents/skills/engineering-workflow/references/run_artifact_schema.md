# M5 run-artifact schema

`build_run_manifest.py` writes two JSON artifacts from the actual M2–M4 files. It does not accept model-generated counts or filtering decisions.

## `exclusions.json`

```json
{
  "schema_version": "1.0",
  "records": [
    {
      "stage": "M3_exact_duplicates",
      "input_records": 0,
      "newly_excluded_records": 0,
      "reason": "exact duplicate activity row",
      "output_records": 0
    }
  ],
  "structure_quality": {
    "structure_records_retrieved": 0,
    "valid_structures": 0,
    "missing_smiles": 0,
    "invalid_smiles": 0
  },
  "final_analyzed_records": 0
}
```

Every `records` item reconciles as `output_records = input_records - newly_excluded_records`; the next stage receives the prior output count. M4 reasons are emitted separately in filter order.

## `run_manifest.json`

```json
{
  "schema_version": "1.0",
  "generated_at": "UTC ISO-8601 timestamp",
  "artifacts": {
    "raw_activities_csv": "absolute path",
    "preparation_metadata_json": "absolute path",
    "statistics_json": "absolute path",
    "exclusions_json": "absolute path"
  },
  "configuration": {
    "acquisition": {"original_target_query": "actual CLI argument"},
    "base_preparation": {},
    "semantic_analysis": {}
  },
  "record_counts": {
    "raw": 0,
    "cleaned": 0,
    "prepared": 0,
    "analyzed": 0,
    "unique_molecules": {"raw": 0, "cleaned": 0, "prepared": 0, "analyzed": 0}
  },
  "software_versions": {}
}
```

The configuration values are copied from M2–M4 metadata generated during the run; file paths and row counts are read from the actual artifacts.
