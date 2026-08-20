# Engineering Workflow

Build reproducible ChEMBL IC50/pIC50 datasets for a confirmed biological target.

The repo-scoped Codex skill is in `.agents/skills/engineering-workflow/`. It resolves a user-supplied target, fetches ChEMBL IC50 activities, validates and transforms records, creates RDKit Morgan fingerprints, and saves a CSV dataset with JSON statistics.

```bash
python .agents/skills/engineering-workflow/scripts/build_chembl_pic50_dataset.py targets --target EGFR
python .agents/skills/engineering-workflow/scripts/build_chembl_pic50_dataset.py dataset --target-id CHEMBL203 --output-dir output/egfr
```

Install dependencies first:

```bash
python -m pip install -r requirements.txt
```
