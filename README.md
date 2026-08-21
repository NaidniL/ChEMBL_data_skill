# Engineering Workflow

Build reproducible ChEMBL IC50/pIC50 datasets for a confirmed biological target.

The repo-scoped Codex skill is in `.agents/skills/engineering-workflow/`. It resolves a user-supplied target, fetches raw ChEMBL activities, cleans and joins them with validated molecular structures, creates RDKit Morgan fingerprints, converts exact IC50 values to pIC50, writes statistics and rankings, and validates the resulting artifact chain with provenance metadata.

```bash
python .agents/skills/engineering-workflow/scripts/discover_target.py --uniprot-accession P00533
python .agents/skills/engineering-workflow/scripts/fetch_activities.py --target-chembl-id CHEMBL203 --activity-type IC50 --output-dir output/raw-egfr
python .agents/skills/engineering-workflow/scripts/prepare_dataset.py --activities-csv output/raw-egfr/activities.csv --output-dir output/prepared-egfr
python .agents/skills/engineering-workflow/scripts/analyze_dataset.py --prepared-csv output/prepared-egfr/prepared_dataset.csv --output-dir output/analysis-egfr
```

Install dependencies first:

```bash
python -m pip install -r requirements.txt
```
