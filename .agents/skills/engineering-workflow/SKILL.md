---
name: engineering-workflow
description: Build a ChEMBL IC50/pIC50 dataset for a biological target. Use when a user asks to resolve a target, retrieve ChEMBL IC50 bioactivities, validate activity records, calculate pIC50, generate RDKit fingerprints, or report dataset exclusions and statistics.
---

# Engineering Workflow

## Workflow

1. Ask for a biological target name, gene symbol, protein name, or ChEMBL target ID. If the requested target or species is ambiguous, do not choose a candidate silently.
2. Resolve a human-readable target and show candidates:

   ```bash
   python .agents/skills/engineering-workflow/scripts/build_chembl_pic50_dataset.py targets --target "EGFR"
   ```

3. Confirm the intended `target_chembl_id` with the user, then build the dataset:

   ```bash
   python .agents/skills/engineering-workflow/scripts/build_chembl_pic50_dataset.py dataset --target-id CHEMBL203 --output-dir output/egfr
   ```

4. Read `statistics.json` and report the final row count, pIC50 range, and every exclusion count. Explain validation failures from the error output; do not claim a dataset was created when the command failed.

Use `--overwrite` only after the user authorizes replacing an existing `dataset.csv` or `statistics.json`.

## Validation policy

The pipeline keeps only IC50 records with exact `=` standard relation, no ChEMBL data-validity flag, a positive numeric value in `pM`, `nM`, `uM`, or `mM`, a molecule ID, and a valid RDKit-parsed canonical SMILES. It converts the accepted values to nM and calculates `pIC50 = 9 - log10(IC50_nM)`. It writes a 2048-bit Morgan fingerprint (radius 2) for each accepted molecule.

Read [references/chembl_data_contract.md](references/chembl_data_contract.md) before changing endpoint fields, filter rules, output columns, or the transformation.
