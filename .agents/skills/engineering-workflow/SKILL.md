---
name: engineering-workflow
description: Build a ChEMBL IC50/pIC50 dataset for a biological target. Use when a user asks to resolve a target, retrieve ChEMBL IC50 bioactivities, validate activity records, calculate pIC50, generate RDKit fingerprints, or report dataset exclusions and statistics.
---

# Engineering Workflow

## Agent Behavior Contract

### Allowed Behaviors

The Agent may:

1. Interpret the user's natural-language request to identify a target name or identifier, organism when stated, requested activity/property, and downstream purpose such as QSAR or exploratory analysis.
2. Use the deterministic workflow scripts to resolve ChEMBL targets; retrieve raw activity data; prepare activity and structure data; generate molecular fingerprints; normalize and analyze IC50/pIC50 data; build provenance and exclusion artifacts; and validate the completed run.
3. Inspect target-discovery candidates and select a candidate only when the match is sufficiently unambiguous from the user's request.
4. Ask the user for clarification when ambiguity could materially change the biological target, organism, activity property, repeated-measurement aggregation, or another scientifically consequential assumption.
5. Select optional metadata fields when they are useful for the user's stated analysis goal.
6. Read generated `run_manifest.json`, `exclusions.json`, `statistics.json`, `top_records.csv`, and `bottom_records.csv` artifacts and use them to summarize the run.
7. Explain the resolved target; acquired and retained record counts; exclusions; measurement transformation; descriptive statistics; high- and low-activity records; and validation warnings or limitations.
8. Distinguish facts contained in deterministic outputs from interpretations or hypotheses suggested by those facts.
9. Stop and report the problem when a deterministic script or validation step fails.
10. Retry network operations only according to the retry behavior implemented by the deterministic acquisition layer. Do not invent retry or fallback semantics.

### Strictly Prohibited Behaviors

The Agent must never:

1. Invent or guess a ChEMBL target ID, UniProt accession, assay ID, molecule ID, activity value, record count, statistic, or other database fact.
2. Replace deterministic pipeline calculations with its own arithmetic or reasoning when an implemented script already performs the operation.
3. Directly modify raw ChEMBL data to make downstream validation pass.
4. Treat a network, API, or cache failure as an empty dataset, a valid zero-result query, or a successful run.
5. Silently choose the first target candidate when multiple biologically plausible candidates remain.
6. Silently substitute another activity type when the requested activity type is unavailable.
7. Treat repeated measurements for the same molecule as duplicate observations.
8. Aggregate repeated measurements unless the user explicitly requires molecule-level aggregation and the aggregation strategy is explicitly defined.
9. Silently select `best`, `mean`, `median`, or any other aggregation strategy.
10. Convert censored measurements such as `<`, `>`, `<=`, or `>=` into exact quantitative measurements.
11. Treat an unknown non-null `data_validity_comment` as automatically valid or automatically invalid.
12. Bypass or weaken the configured validity policy: accepted: null; excluded: `Outside typical range`; unknown non-null values: fail or require review.
13. Change scientific processing rules merely to increase the number of retained records.
14. Change fingerprint type, Morgan radius, fingerprint length, unit policy, filtering rules, or other frozen workflow configuration without explicit user intent and corresponding supported implementation.
15. Recalculate statistics from visually inspected CSV values when `statistics.json` already contains deterministic results.
16. Estimate exclusion counts or final record counts from context. All such numbers must come from generated artifacts.
17. Claim that a workflow completed successfully unless the final independent validation reports PASS.
18. Ignore a validation failure and continue presenting the resulting dataset as trustworthy.
19. Fabricate missing provenance fields in `run_manifest.json`.
20. Present an interpretation as an established biological conclusion when the available data only supports an observation or hypothesis.
21. Modify the Skill implementation, workflow scripts, scientific policies, or validation rules during normal execution unless the user explicitly asks to develop or modify the Skill.
22. Commit, push, publish, or otherwise modify repository history during normal Skill execution unless the user explicitly requests it.

## Workflow

1. Ask for a biological target name, gene symbol, protein name, or ChEMBL target ID. If the requested target or species is ambiguous, do not choose a candidate silently.
2. Resolve a target and show the returned candidates:

   ```bash
   python .agents/skills/engineering-workflow/scripts/discover_target.py --target-name "Epidermal growth factor receptor"
   python .agents/skills/engineering-workflow/scripts/discover_target.py --uniprot-accession P00533
   python .agents/skills/engineering-workflow/scripts/discover_target.py --chembl-target-id CHEMBL203
   ```

3. Confirm the intended `target_chembl_id`, then retrieve the requested raw activity type:

   ```bash
   python .agents/skills/engineering-workflow/scripts/fetch_activities.py --target-chembl-id CHEMBL203 --activity-type IC50 --output-dir output/raw-egfr
   ```

4. Prepare the raw activities and structures:

   ```bash
   python .agents/skills/engineering-workflow/scripts/prepare_dataset.py --activities-csv output/raw-egfr/activities.csv --output-dir output/prepared-egfr
   ```

5. Normalize exact IC50 values and produce statistics and rankings:

   ```bash
   python .agents/skills/engineering-workflow/scripts/analyze_dataset.py --prepared-csv output/prepared-egfr/prepared_dataset.csv --output-dir output/analysis-egfr
   ```

6. Build the deterministic provenance and exclusion artifacts, then validate them independently:

   ```bash
   python .agents/skills/engineering-workflow/scripts/build_run_manifest.py \
     --original-target-query P00533 \
     --raw-activities-csv output/raw-egfr/activities.csv \
     --raw-metadata-json output/raw-egfr/metadata.json \
     --cleaned-activities-csv output/prepared-egfr/activities_clean.csv \
     --structures-csv output/prepared-egfr/structures.csv \
     --preparation-metadata-json output/prepared-egfr/preparation_metadata.json \
     --prepared-csv output/prepared-egfr/prepared_dataset.csv \
     --analyzed-csv output/analysis-egfr/analyzed_dataset.csv \
     --statistics-json output/analysis-egfr/statistics.json \
     --top-records-csv output/analysis-egfr/top_records.csv \
     --bottom-records-csv output/analysis-egfr/bottom_records.csv \
     --output-dir output/validation-egfr

   python .agents/skills/engineering-workflow/scripts/validate_run.py \
     --run-manifest-json output/validation-egfr/run_manifest.json \
     --report-json output/validation-egfr/validation_report.json
   ```

7. Read `validation_report.json`, `exclusions.json`, and `statistics.json` before summarizing the run. Report validation errors exactly as written; do not infer a correction or claim a valid dataset when `valid` is false.

Use `--overwrite` only after the user authorizes replacing an existing `dataset.csv` or `statistics.json`.

## Target discovery script

`scripts/discover_target.py` accepts exactly one of `--target-name`, `--uniprot-accession`, or `--chembl-target-id`, plus optional `--organism`. It emits JSON with the input metadata and a `candidates` list containing zero or more ChEMBL records with `target_chembl_id`, `organism`, `pref_name`, and `target_type`.

Use this script only for discovery. Do not add local candidate filtering, sorting, deduplication, deletion, or field-value changes. The optional organism is a ChEMBL query constraint, not a local post-processing filter.

## Raw activity acquisition script

`scripts/fetch_activities.py` accepts a confirmed `--target-chembl-id` and `--activity-type`, then saves `activities.csv` and `metadata.json`. The ChEMBL client cache is disabled by default and recorded in metadata as `client_cache_enabled: false`; `--use-cache` is an explicit opt-in. It keeps only the documented raw schema; it does not clean missing values, deduplicate, convert units, transform values, or infer a substitute activity type.

## Data preparation and structure integration script

`scripts/prepare_dataset.py` accepts an M2 `activities.csv`. It converts required numeric fields, drops rows missing M3-required activity fields, removes exact duplicate rows, and keeps repeated measurements for the same molecule. It retrieves one ChEMBL structure per retained molecule, writes all structure statuses (`valid`, `missing_smiles`, or `invalid_smiles`), and merges only valid structures. The prepared dataset contains a Morgan fingerprint with radius 2 and 2048 bits, serialized as `bitstring:<bits>`. It does not convert units or calculate pIC50; those are M4 operations.

## IC50 analysis script

`scripts/analyze_dataset.py` supports IC50 only. It preserves `standard_value` and `standard_units`, accepts only null `data_validity_comment` values, excludes `Outside typical range`, and fails with the affected values and activity IDs when any other non-null comment requires review. It then retains exact `=` rows with a positive finite value and a supported unit (`pM`, `nM`, `uM`/`µM`/`μM`, or `mM`). It adds `ic50_nM` and `pIC50 = 9 - log10(IC50_nM)`, writes count/mean/median/standard deviation/quartiles/minimum/maximum for both metrics, and creates full-metadata top/bottom CSV files ranked by pIC50.

## Validation and provenance scripts

`scripts/build_run_manifest.py` derives `run_manifest.json` and `exclusions.json` only from CLI arguments, M2–M4 metadata, CSV row counts, and installed package versions. `exclusions.json` records each stage transition as input count, newly excluded count, reason, and output count. `scripts/validate_run.py` independently reads the manifest artifacts and emits a JSON report with `valid`, a concise message, summary counts, and actionable errors. Read [references/run_artifact_schema.md](references/run_artifact_schema.md) for the JSON schema.

Do not change endpoint fields, filtering rules, output columns, or fingerprint parameters without updating the corresponding deterministic script and tests.
