# Project Progress

This file tracks implementation progress against `docs/workflow_spec.md`.

Status convention:

* `[ ]` Not started
* `[-]` In progress / partially implemented
* `[x]` Implemented and validated

A feature is only marked `[x]` after both implementation and the relevant validation/tests are complete.

---

## Current Status

**Current phase:** Phase 1 — Discover & Acquire

**Current milestone:** M3 — Data Preparation and Structure Integration

Completed project setup:

* [x] Initial workflow specification written
* [x] Python environment requirements defined
* [x] Core dependencies selected
* [ ] Repository execution pipeline implemented
* [x] Codex Skill target-discovery entry point implemented
* [ ] Streamlit interface implemented

Current dependency baseline:

```text
Python 3.11–3.13

chembl_webresource_client>=0.10.9
numpy>=1.26,<3
pandas>=2.2,<4
rdkit>=2024.9,<2027
```

---

# Milestones

## M0 — Specification and Environment

Goal: define the workflow before implementation.

* [x] Define project purpose
* [x] Define Version 0.1 scope
* [x] Define non-goals
* [x] Split workflow into three phases
* [x] Define Agent vs. deterministic-code boundary
* [x] Define duplicate/repeated-measurement policy
* [x] Define missing-value policy
* [x] Define IC50/pIC50 semantics
* [x] Define initial output and validation requirements
* [x] Create `requirements.txt`
* [x] Prepare Python environment

**Status:** complete

---

## M1 — Target Discovery

Goal: reliably convert a target identifier/query into structured ChEMBL target candidates.

Planned entry point:

```text
scripts/discover_target.py
```

### Implementation

* [x] Accept exactly one target query
* [x] Support UniProt accession input
* [x] Support ChEMBL target ID input
* [x] Support exact ChEMBL preferred target-name lookup; fuzzy expansion is intentionally deferred
* [x] Query ChEMBL target data
* [x] Return the fixed candidate-field schema from ChEMBL
* [x] Return all candidates instead of silently selecting the first
* [x] Produce structured machine-readable JSON output

Expected candidate fields:

```text
target_chembl_id
pref_name
organism
target_type
```

### Error handling

* [x] Reject empty or malformed identifier input
* [x] Return an empty `candidates` list for no-match results
* [x] Return multiple plausible candidates unchanged
* [x] Handle API/network failure clearly
* [x] Avoid silently replacing unresolved targets

### Tests

* [x] Unit test input validation
* [x] Offline test preserves the candidate list and output contract
* [x] Offline test covers multiple-candidate handling without a ChEMBL request
* [x] Integration test with human EGFR / P00533

### Completion condition

```text
P00533
→ discover_target.py
→ structured candidate result containing the expected human EGFR target
```

**Status:** complete

---

## M2 — Raw Activity Acquisition

Goal: retrieve and preserve raw ChEMBL activity records for a resolved target.

Planned entry point:

```text
scripts/fetch_activities.py
```

### Implementation

* [x] Accept resolved ChEMBL target ID
* [x] Accept requested activity type
* [x] Query ChEMBL activity records
* [x] Verify returned standard activity type matches the request
* [x] Preserve returned standard units for later inspection
* [x] Preserve returned relation operators for later inspection
* [x] Define and verify the agreed core activity columns
* [x] Restrict Version 0.1 raw output to the agreed core schema
* [x] Convert API response into a pandas DataFrame
* [x] Preserve raw data without destructive processing
* [x] Save raw activity data and metadata
* [x] Disable ChEMBL client cache by default and record its setting in metadata

Expected artifact:

```text
outputs/raw/activities.csv
```

### Validation

* [x] Required raw fields exist
* [x] Retrieved target matches requested target
* [x] Requested activity type is available
* [x] Raw record count is recorded
* [x] Empty datasets fail clearly

### Completion condition

```text
resolved target
+ activity type
→ ChEMBL
→ reproducible raw activities.csv
```

**Status:** complete

---

## M3 — Data Preparation and Structure Integration

Goal: convert raw activity data into a clean structure-associated dataset.

Planned entry point:

```text
scripts/prepare_dataset.py
```

### Activity-data preparation

* [x] Convert required fields to appropriate data types
* [x] Detect numeric conversion failures
* [x] Apply required-field missing-value policy
* [x] Preserve optional-field missingness
* [x] Remove exact duplicate observations
* [x] Preserve legitimate repeated measurements
* [x] Reset/rebuild indexes where appropriate
* [x] Normalize column names

### Repeated-measurement handling

* [x] Distinguish exact duplicates from repeated biological measurements
* [x] Default to `keep_all`
* [x] Do not silently choose `best`
* [x] Do not silently aggregate repeated measurements
* [x] Record the `keep_all` aggregation strategy

### Structure acquisition

* [x] Extract unique molecule ChEMBL IDs
* [x] Fetch molecular structure data
* [x] Retain canonical SMILES
* [x] Mark missing structure records and exclude them from prepared data
* [x] Parse SMILES with RDKit
* [x] Mark invalid RDKit molecules and exclude them from prepared data
* [x] Enforce one structure record per molecule ID
* [x] Preserve structure exclusion counts

### Fingerprints

* [x] Select Morgan bit fingerprints
* [x] Define radius 2 and length 2048 explicitly
* [x] Generate fingerprints from valid RDKit molecules
* [x] Validate consistent fingerprint dimensions
* [x] Record fingerprint configuration
* [x] Store prefixed bitstrings in the prepared CSV

### Merge

* [x] Merge activity and structure data using `molecule_chembl_id`
* [x] Validate one structure record per merge key
* [x] Record rows before and after merge
* [x] Record activity rows lost because no valid structure was available

### Completion condition

```text
raw activity data
+ ChEMBL structures
→ cleaned activity data
→ validated structures
→ fingerprints
→ merged analysis-ready dataset
```

**Status:** complete

---

## M4 — Property Interpretation and Analysis

Goal: transform and summarize the requested quantitative property.

Planned entry point:

```text
scripts/analyze_dataset.py
```

### Property handling

* [x] Accept IC50 as the selected activity property
* [x] Define lower IC50 / higher pIC50 as stronger activity
* [x] Distinguish raw IC50 from normalized and transformed fields
* [x] Preserve raw measurements

### Unit handling

* [x] Inspect units
* [x] Convert pM, nM, uM/µM/μM, and mM to nM
* [x] Detect unsupported units
* [x] Record conversion/exclusion counts

### IC50 / pIC50

* [x] Require finite positive IC50 before logarithmic transformation
* [x] Implement IC50 → pIC50 after nM normalization
* [x] Implement/verify nM shortcut

Regression cases:

* [x] `1 nM → 9`
* [x] `100 nM → 7`
* [x] `1000 nM → 6`

### Relation operators

* [x] Preserve scientific meaning of `<`, `>`, `<=`, `>=`
* [x] Do not convert censored measurements into exact values
* [x] Default Version 0.1 quantitative dataset to exact `=` records
* [x] Record excluded censored measurements

### Statistics

* [x] Count records
* [x] Count unique molecules
* [x] Count missing standard values as exclusions
* [x] Calculate mean
* [x] Calculate median
* [x] Calculate standard deviation
* [x] Calculate minimum/maximum
* [x] Calculate quartiles

### Ranking

* [x] Generate top-N records
* [x] Generate bottom-N records
* [x] Use pIC50 descending/ascending directions
* [x] Include all analyzed metadata in ranked records

### Completion condition

```text
prepared dataset
+ selected property
→ normalized values
→ transformed values
→ descriptive statistics
→ ranked records
```

**Status:** complete

---

## M5 — Validation, Provenance, and Regression Tests

Goal: make the pipeline auditable and resistant to silent failure.

### Validation invariants

* [x] Required columns exist
* [x] Required fields contain no unexpected missing values
* [x] Quantitative values are numeric
* [x] Log-transformed values originate from positive measurements
* [x] Units are consistent after normalization
* [x] Molecule IDs are present
* [x] SMILES are RDKit-parseable
* [x] Fingerprints are valid
* [x] Fingerprint dimensions are consistent
* [x] Merge counts reconcile
* [x] Final reported row counts reconcile with exclusions

### Exclusion accounting

Track counts for at least:

* [x] wrong activity type
* [x] non-exact/censored relation
* [x] missing required value
* [x] invalid numeric value
* [x] unsupported unit
* [x] missing structure
* [x] invalid SMILES
* [x] exact duplicate
* [x] merge loss

### Run metadata

* [x] Record original target query
* [x] Record resolved target and ChEMBL target ID
* [x] Record selected activity property
* [x] Record filters
* [x] Record aggregation strategy
* [x] Record unit-conversion policy
* [x] Record fingerprint configuration
* [x] Record raw/final record counts
* [x] Record unique molecule counts
* [x] Record execution timestamp
* [x] Record relevant package versions

Proposed artifacts:

```text
outputs/statistics.json
outputs/exclusions.json
outputs/run_manifest.json
```

### Regression testing

* [x] Unit tests run without requiring live ChEMBL access
* [x] Network/integration tests are separable from unit tests
* [x] At least one known-target integration case exists
* [ ] At least one second target verifies that the pipeline is not EGFR-specific
* [x] Previous working cases remain green after modifications

**Status:** complete

---

## M6 — Codex Skill Integration

Goal: expose the deterministic workflow through natural-language interaction.

Proposed location:

```text
.agents/
└── skills/
    └── chembl-dataset/
        ├── SKILL.md
        ├── scripts/
        └── references/
```

Exact structure may be revised after the deterministic pipeline is stable.

### Skill behavior

* [ ] Define clear Skill name and description
* [ ] Define activation/use cases
* [ ] Define required user information
* [ ] Map natural-language target requests to target discovery
* [ ] Map natural-language analysis intent to activity property
* [ ] Select useful optional metadata
* [ ] Invoke deterministic scripts instead of reproducing their calculations
* [ ] Ask for confirmation only for scientifically consequential ambiguity
* [ ] Interpret statistics and ranked records
* [ ] Distinguish observations from interpretations
* [ ] Explain exclusions and warnings
* [ ] Avoid unsupported biological conclusions

### Fresh-session validation

A fresh Codex session should successfully handle a request similar to:

```text
Build a ChEMBL IC50 dataset for human EGFR for later QSAR analysis.
```

without requiring the user to know:

* ChEMBL target ID;

* API syntax;

* DataFrame field names;

* pIC50 calculation details;

* structure-table join details.

* [ ] Skill is discovered by Codex

* [ ] Natural-language request is interpreted correctly

* [ ] Appropriate target is resolved

* [ ] Correct pipeline steps are invoked

* [ ] Final artifacts are produced

* [ ] Final summary matches deterministic outputs

* [ ] No unsupported facts are invented

**Status:** not started

---

## M7 — Optional Interface

Goal: provide a simple interface for non-Codex users after the core Skill is stable.

Potential implementation:

```text
Streamlit
```

* [ ] Define minimal UI requirements
* [ ] Reuse the same workflow core
* [ ] Avoid duplicating pipeline logic in the UI
* [ ] Display execution progress
* [ ] Display statistics and warnings
* [ ] Allow relevant outputs to be saved/exported

This milestone is optional for Version 0.1 and should not delay completion of the core Skill.

**Status:** not started

---

# Acceptance Criteria

These correspond to Section 30 of `workflow_spec.md`.

* [ ] **AC01** — A user can provide a target through natural language.
* [ ] **AC02** — The workflow can resolve an appropriate ChEMBL target.
* [ ] **AC03** — The workflow can retrieve the requested activity type.
* [ ] **AC04** — The raw activity dataset is preserved.
* [x] **AC05** — Required activity fields are cleaned deterministically.
* [x] **AC06** — Repeated measurements are not silently collapsed.
* [x] **AC07** — Molecular structures are retrieved and validated.
* [x] **AC08** — Invalid or missing structures are handled explicitly.
* [x] **AC09** — RDKit fingerprints are generated with recorded parameters.
* [x] **AC10** — Activity and structure datasets are merged reproducibly.
* [x] **AC11** — IC50 values are standardized and converted to pIC50 correctly.
* [x] **AC12** — Descriptive statistics are generated deterministically.
* [x] **AC13** — High/low activity records are ranked with the correct direction.
* [x] **AC14** — Every destructive filtering stage reports exclusion counts.
* [x] **AC15** — The final dataset passes defined validation checks.
* [ ] **AC16** — The Agent summarizes the run without inventing information.
* [ ] **AC17** — A fresh Codex session can use the Skill without requiring knowledge of ChEMBL API details or internal column names.

Current acceptance progress:

```text
Implemented and validated: 11 / 17
```

---

# Development Cases

## Primary development case

Reference workflow:

```text
Human EGFR
UniProt: P00533
```

Purpose:

* reproduce the essential TeachOpenCADD T001 workflow;
* provide a known development target;
* establish initial integration tests.

Status:

* [x] Target discovery
* [x] Activity acquisition
* [x] Data preparation
* [x] Structure acquisition
* [x] Fingerprint generation
* [x] IC50/pIC50 processing
* [x] Statistics
* [ ] End-to-end validation

---

## Generalization case

A second molecular target must be selected after the primary case works.

Purpose:

* detect EGFR-specific hard-coding;
* verify target-independent pipeline behavior;
* test variation in ChEMBL activity data.

Status:

* [ ] Second target selected
* [ ] Target discovery passes
* [ ] Activity acquisition passes
* [ ] Preparation passes
* [ ] Analysis passes
* [ ] End-to-end validation passes

---

# Immediate Next Step

Integrate the deterministic pipeline with the Codex Skill:

```text
.agents/skills/engineering-workflow/
```

First target:

```text
M1–M5 artifacts
```

Target milestone:

```text
natural-language request
→ deterministic M1–M5 execution
→ evidence-grounded summary
```

Do not add an interface until the Skill can invoke and summarize M1–M5 reliably.
