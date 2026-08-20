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

4. Read `metadata.json` and report the record count, raw columns, and cache setting. The client cache is disabled by default; use `--use-cache` only when the user explicitly requests it. Explain validation failures from the error output; do not claim a dataset was created when the command failed.

Use `--overwrite` only after the user authorizes replacing an existing `dataset.csv` or `statistics.json`.

## Target discovery script

`scripts/discover_target.py` accepts exactly one of `--target-name`, `--uniprot-accession`, or `--chembl-target-id`, plus optional `--organism`. It emits JSON with the input metadata and a `candidates` list containing zero or more ChEMBL records with `target_chembl_id`, `organism`, `pref_name`, and `target_type`.

Use this script only for discovery. Do not add local candidate filtering, sorting, deduplication, deletion, or field-value changes. The optional organism is a ChEMBL query constraint, not a local post-processing filter.

## Raw activity acquisition script

`scripts/fetch_activities.py` accepts a confirmed `--target-chembl-id` and `--activity-type`, then saves `activities.csv` and `metadata.json`. The ChEMBL client cache is disabled by default and recorded in metadata as `client_cache_enabled: false`; `--use-cache` is an explicit opt-in. It keeps only the documented raw schema; it does not clean missing values, deduplicate, convert units, transform values, or infer a substitute activity type.

## Validation policy

The pipeline keeps only IC50 records with exact `=` standard relation, no ChEMBL data-validity flag, a positive numeric value in `pM`, `nM`, `uM`, or `mM`, a molecule ID, and a valid RDKit-parsed canonical SMILES. It converts the accepted values to nM and calculates `pIC50 = 9 - log10(IC50_nM)`. It writes a 2048-bit Morgan fingerprint (radius 2) for each accepted molecule.

Read [references/chembl_data_contract.md](references/chembl_data_contract.md) before changing endpoint fields, filter rules, output columns, or the transformation.
