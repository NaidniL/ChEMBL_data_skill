# Engineering Workflow

Build reproducible ChEMBL IC50/pIC50 datasets for a confirmed biological target.

The repo-scoped Codex skill is in `.agents/skills/chembl-workflow/`. It resolves a user-supplied target, fetches raw ChEMBL activities, cleans and joins them with validated molecular structures, creates RDKit Morgan fingerprints, converts exact IC50 values to pIC50, writes statistics and rankings, and validates the resulting artifact chain with provenance metadata.

`tests/fixtures/egfr-limit20/` contains an offline regression fixture. `examples/expected_output/` contains two validated end-to-end EGFR example runs.

```bash
python .agents/skills/chembl-workflow/scripts/discover_target.py --uniprot-accession P00533
python .agents/skills/chembl-workflow/scripts/fetch_activities.py --target-chembl-id CHEMBL203 --activity-type IC50 --output-dir output/raw-egfr
python .agents/skills/chembl-workflow/scripts/prepare_dataset.py --activities-csv output/raw-egfr/activities.csv --output-dir output/prepared-egfr
python .agents/skills/chembl-workflow/scripts/analyze_dataset.py --prepared-csv output/prepared-egfr/prepared_dataset.csv --output-dir output/analysis-egfr
```

Install dependencies first:

```bash
python -m pip install -r requirements.txt
```

Run the presentation layer from the isolated environment:

```bash
.venv/bin/streamlit run app.py
```

Each Streamlit invocation runs the deterministic CLI stages and writes its artifacts to a separate timestamped directory under `runs/`. Live ChEMBL runs default to a positive record limit of 200, configurable in the UI. The offline option lets users choose a valid fixture directory directly under `tests/fixtures/` and makes no ChEMBL request.
