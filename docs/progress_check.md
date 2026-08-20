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

* [ ] Convert required fields to appropriate data types
* [ ] Detect numeric conversion failures
* [ ] Apply required-field missing-value policy
* [ ] Preserve optional-field missingness
* [ ] Remove exact duplicate observations
* [ ] Preserve legitimate repeated measurements
* [ ] Reset/rebuild indexes where appropriate
* [ ] Normalize column names

### Repeated-measurement handling

* [ ] Distinguish exact duplicates from repeated biological measurements
* [ ] Default to `keep_all`
* [ ] Do not silently choose `best`
* [ ] Do not silently aggregate repeated measurements
* [ ] Record aggregation strategy when aggregation is explicitly requested

### Structure acquisition

* [ ] Extract unique molecule ChEMBL IDs
* [ ] Fetch molecular structure data
* [ ] Retain canonical SMILES
* [ ] Remove/flag missing structure records
* [ ] Parse SMILES with RDKit
* [ ] Remove/flag invalid RDKit molecules
* [ ] Remove equivalent structure-table duplicates by molecule ID when appropriate
* [ ] Preserve structure exclusion counts

### Fingerprints

* [ ] Select initial fingerprint representation
* [ ] Define fingerprint parameters explicitly
* [ ] Generate fingerprints from valid RDKit molecules
* [ ] Validate consistent fingerprint dimensions
* [ ] Record fingerprint configuration
* [ ] Decide storage format for fingerprints

### Merge

* [ ] Merge activity and structure data using `molecule_chembl_id`
* [ ] Validate merge keys
* [ ] Record rows before and after merge
* [ ] Record activity rows lost because no valid structure was available

### Completion condition

```text
raw activity data
+ ChEMBL structures
→ cleaned activity data
→ validated structures
→ fingerprints
→ merged analysis-ready dataset
```

**Status:** not started

---

## M4 — Property Interpretation and Analysis

Goal: transform and summarize the requested quantitative property.

Planned entry point:

```text
scripts/analyze_dataset.py
```

### Property handling

* [ ] Accept selected activity property
* [ ] Define scientific direction of the property
* [ ] Distinguish raw and transformed properties
* [ ] Preserve raw measurements

### Unit handling

* [ ] Inspect units
* [ ] Convert supported units to a canonical scale
* [ ] Detect unsupported units
* [ ] Record conversion/exclusion counts

### IC50 / pIC50

* [ ] Require positive IC50 before logarithmic transformation
* [ ] Implement molar IC50 → pIC50
* [ ] Implement/verify nM shortcut

Regression cases:

* [ ] `1 nM → 9`
* [ ] `100 nM → 7`
* [ ] `1000 nM → 6`

### Relation operators

* [ ] Preserve scientific meaning of `<`, `>`, `<=`, `>=`
* [ ] Do not convert censored measurements into exact values
* [ ] Default Version 0.1 quantitative dataset to exact `=` records where appropriate
* [ ] Record excluded censored measurements

### Statistics

* [ ] Count records
* [ ] Count unique molecules
* [ ] Count missing values
* [ ] Calculate mean
* [ ] Calculate median
* [ ] Calculate standard deviation
* [ ] Calculate minimum/maximum
* [ ] Calculate quartiles

### Ranking

* [ ] Generate top-N records
* [ ] Generate bottom-N records
* [ ] Use the scientifically correct sorting direction
* [ ] Include useful metadata for ranked records

### Completion condition

```text
prepared dataset
+ selected property
→ normalized values
→ transformed values
→ descriptive statistics
→ ranked records
```

**Status:** not started

---

## M5 — Validation, Provenance, and Regression Tests

Goal: make the pipeline auditable and resistant to silent failure.

### Validation invariants

* [ ] Required columns exist
* [ ] Required fields contain no unexpected missing values
* [ ] Quantitative values are numeric
* [ ] Log-transformed values originate from positive measurements
* [ ] Units are consistent after normalization
* [ ] Molecule IDs are present
* [ ] SMILES are RDKit-parseable
* [ ] Fingerprints are valid
* [ ] Fingerprint dimensions are consistent
* [ ] Merge counts reconcile
* [ ] Final reported row counts reconcile with exclusions

### Exclusion accounting

Track counts for at least:

* [ ] wrong activity type
* [ ] non-exact/censored relation
* [ ] missing required value
* [ ] invalid numeric value
* [ ] unsupported unit
* [ ] missing structure
* [ ] invalid SMILES
* [ ] exact duplicate
* [ ] merge loss

### Run metadata

* [ ] Record original target query
* [ ] Record resolved target
* [ ] Record ChEMBL target ID
* [ ] Record selected activity property
* [ ] Record filters
* [ ] Record aggregation strategy
* [ ] Record unit-conversion policy
* [ ] Record fingerprint configuration
* [ ] Record raw/final record counts
* [ ] Record unique molecule counts
* [ ] Record execution timestamp
* [ ] Record relevant package versions where practical

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

**Status:** not started

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
* [ ] **AC05** — Required activity fields are cleaned deterministically.
* [ ] **AC06** — Repeated measurements are not silently collapsed.
* [ ] **AC07** — Molecular structures are retrieved and validated.
* [ ] **AC08** — Invalid or missing structures are handled explicitly.
* [ ] **AC09** — RDKit fingerprints are generated with recorded parameters.
* [ ] **AC10** — Activity and structure datasets are merged reproducibly.
* [ ] **AC11** — IC50 values are standardized and converted to pIC50 correctly.
* [ ] **AC12** — Descriptive statistics are generated deterministically.
* [ ] **AC13** — High/low activity records are ranked with the correct direction.
* [ ] **AC14** — Every destructive filtering stage reports exclusion counts.
* [ ] **AC15** — The final dataset passes defined validation checks.
* [ ] **AC16** — The Agent summarizes the run without inventing information.
* [ ] **AC17** — A fresh Codex session can use the Skill without requiring knowledge of ChEMBL API details or internal column names.

Current acceptance progress:

```text
Implemented and validated: 0 / 17
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
* [ ] Activity acquisition
* [ ] Data preparation
* [ ] Structure acquisition
* [ ] Fingerprint generation
* [ ] IC50/pIC50 processing
* [ ] Statistics
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

Implement data preparation and structure integration:

```text
scripts/prepare_dataset.py
```

First target:

```text
outputs/raw/activities.csv
```

Target milestone:

```text
raw activity data
+ molecular structures
→ cleaned structure-associated dataset
```

Do not proceed to activity cleaning, RDKit fingerprints, or Streamlit until this boundary works reliably.
