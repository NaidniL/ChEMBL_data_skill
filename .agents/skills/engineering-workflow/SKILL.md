---
name: engineering-workflow
description: Build a ChEMBL IC50/pIC50 dataset for a biological target. Use when a user asks to resolve a target, retrieve ChEMBL IC50 bioactivities, validate activity records, calculate pIC50, generate RDKit fingerprints, or report dataset exclusions and statistics.
---

# Engineering Workflow

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

5. Read `preparation_metadata.json` and report activity exclusions, structure-status counts, merge counts, fingerprint configuration, and cache setting. The client cache is disabled by default; use `--use-cache` only when the user explicitly requests it. Explain validation failures from the error output; do not claim a dataset was created when the command failed.

Use `--overwrite` only after the user authorizes replacing an existing `dataset.csv` or `statistics.json`.

## Target discovery script

`scripts/discover_target.py` accepts exactly one of `--target-name`, `--uniprot-accession`, or `--chembl-target-id`, plus optional `--organism`. It emits JSON with the input metadata and a `candidates` list containing zero or more ChEMBL records with `target_chembl_id`, `organism`, `pref_name`, and `target_type`.

Use this script only for discovery. Do not add local candidate filtering, sorting, deduplication, deletion, or field-value changes. The optional organism is a ChEMBL query constraint, not a local post-processing filter.

## Raw activity acquisition script

`scripts/fetch_activities.py` accepts a confirmed `--target-chembl-id` and `--activity-type`, then saves `activities.csv` and `metadata.json`. The ChEMBL client cache is disabled by default and recorded in metadata as `client_cache_enabled: false`; `--use-cache` is an explicit opt-in. It keeps only the documented raw schema; it does not clean missing values, deduplicate, convert units, transform values, or infer a substitute activity type.

## Data preparation and structure integration script

`scripts/prepare_dataset.py` accepts an M2 `activities.csv`. It converts required numeric fields, drops rows missing M3-required activity fields, removes exact duplicate rows, and keeps repeated measurements for the same molecule. It retrieves one ChEMBL structure per retained molecule, writes all structure statuses (`valid`, `missing_smiles`, or `invalid_smiles`), and merges only valid structures. The prepared dataset contains a Morgan fingerprint with radius 2 and 2048 bits, serialized as `bitstring:<bits>`. It does not convert units or calculate pIC50; those are M4 operations.

## M4 validation policy (planned)

M4 will keep only IC50 records with exact `=` standard relation, no ChEMBL data-validity flag, a positive numeric value in `pM`, `nM`, `uM`, or `mM`, a molecule ID, and a valid RDKit-parsed canonical SMILES. It will convert accepted values to nM and calculate `pIC50 = 9 - log10(IC50_nM)`.

Do not change endpoint fields, filtering rules, output columns, or fingerprint parameters without updating the corresponding deterministic script and tests.
