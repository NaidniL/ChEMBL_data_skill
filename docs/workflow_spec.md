# Workflow Specification

## 1. Purpose

This project turns a common early-stage cheminformatics workflow into a reusable Codex Skill.

The Skill should allow a user to describe a molecular target and an analysis goal in natural language, then automatically:

1. identify the relevant target in public databases;
2. discover and retrieve appropriate ChEMBL bioactivity data;
3. clean and integrate activity and molecular structure data;
4. standardize the selected activity property;
5. generate molecular representations required by downstream analysis;
6. calculate descriptive statistics and rank relevant records;
7. summarize the resulting dataset and important data-quality considerations.

The user should not need to know:

* ChEMBL API syntax;
* exact ChEMBL field names;
* which metadata columns are required;
* how activity and structure tables should be joined;
* how molecular structures are parsed with RDKit;
* how common activity measurements should be transformed;
* which metadata may be useful when interpreting high- or low-value records.

The Skill acts as an orchestration and interpretation layer around a deterministic data-processing pipeline.

---

## 2. Scope of Version 0.1

Version 0.1 focuses on:

* ChEMBL as the bioactivity and compound-data source;
* molecular targets resolvable from a target name, UniProt accession, or ChEMBL target identifier;
* quantitative molecular bioactivity data;
* compound structures represented by canonical SMILES;
* RDKit-compatible molecular fingerprints;
* common tabular cleaning and integration;
* unit standardization and mathematical transformation of selected activity properties;
* descriptive statistics and ranking.

The first implementation should prioritize IC50 / pIC50 workflows because this is the workflow used as the initial development and test case.

The architecture should nevertheless avoid hard-coding IC50-specific assumptions into general data-acquisition and preparation components.

---

## 3. Non-goals

Version 0.1 is not intended to:

* support every public chemistry database;
* replace ChEMBL's own data-quality annotations;
* automatically decide whether measurements from biologically different assays are directly comparable;
* automatically collapse all measurements for the same molecule into one value;
* perform QSAR or machine-learning model training;
* perform molecular docking or molecular dynamics;
* perform advanced chemical standardization beyond the requirements of the current workflow;
* provide authoritative biological conclusions from activity values alone;
* hide uncertainty in target resolution, assay context, units, or repeated measurements.

When the requested analysis requires assumptions outside the supported workflow, the Skill should explain the limitation instead of silently making the decision.

---

# 4. High-level Workflow

```text
Natural-language request
        │
        ▼
┌─────────────────────────────┐
│ Phase 1 — Discover & Acquire│
│                             │
│ Understand user intent      │
│ Resolve target              │
│ Explore available data      │
│ Select relevant records     │
│ Download raw activity data  │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ Phase 2 — Prepare & Integrate│
│                              │
│ Type conversion              │
│ Missing-value handling       │
│ Duplicate handling           │
│ Structure acquisition        │
│ SMILES validation            │
│ Fingerprint generation       │
│ Schema normalization         │
│ Dataset merge                │
└──────────────┬───────────────┘
               │
               ▼
┌─────────────────────────────┐
│ Phase 3 — Interpret & Analyze│
│                              │
│ Select property              │
│ Standardize units            │
│ Transform values             │
│ Compute statistics           │
│ Rank records                 │
│ Interpret useful metadata    │
└──────────────┬───────────────┘
               │
               ▼
        Analysis-ready data
        + statistics
        + run summary
```

---

# 5. Design Principle: Agent vs. Deterministic Code

The project deliberately separates semantic reasoning from deterministic data processing.

## 5.1 Tasks handled by the Agent

The Agent may:

* interpret the user's natural-language research goal;
* extract target names or identifiers;
* infer which activity property is relevant;
* identify which optional metadata may help answer the user's question;
* inspect small discovery-query results;
* select among candidate ChEMBL targets;
* explain ambiguity;
* decide when user confirmation is necessary;
* interpret statistics and ranked records;
* identify potentially informative relationships between activity values and metadata;
* explain exclusions, warnings, and limitations.

## 5.2 Tasks handled by deterministic code

Python code must handle:

* API requests;
* DataFrame construction;
* column validation;
* type conversion;
* missing-value filtering;
* exact duplicate removal;
* joins;
* unit conversion;
* mathematical transformations;
* RDKit molecule parsing;
* fingerprint generation;
* sorting;
* descriptive statistics;
* file writing;
* invariant checking.

An LLM must not be used for arithmetic or tabular transformations when the same operation can be implemented deterministically.

---

# 6. Inputs

## 6.1 User-facing input

The Skill should accept natural-language requests such as:

```text
I want to obtain human EGFR IC50 data from ChEMBL for later QSAR analysis.
```

```text
Build a dataset for this UniProt target and show me the most active compounds.
```

```text
Download activity data for CHEMBL203 and prepare the IC50 values for analysis.
```

The user should not be required to provide ChEMBL column names.

---

## 6.2 Information extracted from the request

The Agent should attempt to identify:

* target name;
* target organism, if specified;
* UniProt accession, if specified;
* ChEMBL target identifier, if specified;
* activity/property of interest;
* downstream purpose;
* whether one record per measurement or one record per molecule is required;
* whether specific assay metadata is important.

Unknown fields may remain unspecified.

The Agent should ask the user only when an unresolved ambiguity could materially change the resulting dataset.

---

# 7. Phase 1 — Discover & Acquire

## 7.1 Goal

Resolve the biological target and retrieve the raw activity records needed for the requested task.

This phase distinguishes between:

```text
discovery queries
```

and:

```text
dataset acquisition
```

Discovery queries should be small and inexpensive. Full data retrieval should only occur once the intended target and data type are sufficiently resolved.

---

## 7.2 Target resolution

Possible starting identifiers include:

* ChEMBL target ID;
* UniProt accession;
* target/gene/protein name.

Target discovery should return a compact candidate table containing sufficient information to distinguish candidates, for example:

* ChEMBL target ID;
* preferred target name;
* organism;
* target type;
* associated identifier information when available.

The Agent evaluates these candidates in the context of the user's request.

### Confirmation rule

Explicit user confirmation is required when:

* multiple biologically plausible targets remain;
* organism is ambiguous;
* target type changes the interpretation substantially;
* the Agent cannot confidently determine the intended target.

Confirmation is not required when an exact ChEMBL target ID was supplied and successfully resolved.

---

## 7.3 Activity discovery

After target resolution, the workflow should inspect available activity records before downloading the final dataset.

The discovery step should determine at least:

* available standard activity types;
* approximate record counts;
* available standard units;
* presence of exact and censored measurements;
* availability of molecule identifiers.

This allows the Agent to determine whether the user's requested property is actually available.

---

## 7.4 Column-selection policy

Users should not manually select API fields.

Column selection follows:

```text
CORE_COLUMNS
+
OPTIONAL_COLUMNS selected from user intent
```

### Core activity fields

The initial core schema should include fields equivalent to:

```text
molecule_chembl_id
target_chembl_id
assay_chembl_id

standard_type
standard_relation
standard_value
standard_units

pchembl_value

data_validity_comment
potential_duplicate
```

Exact API field names should be verified during implementation.

### Optional fields

Additional metadata may be retained when useful to the user's analysis, including examples such as:

```text
assay_type
assay_description
document_chembl_id
target organism
target preferred name
```

The Agent decides whether optional fields are useful based on the stated analysis goal.

Whenever practical, API acquisition should retrieve a sufficiently rich raw dataset and perform task-specific column reduction locally instead of repeatedly querying the API for different small schemas.

---

## 7.5 Raw activity output

Phase 1 produces an unprocessed activity DataFrame.

A raw copy should be retained before destructive cleaning whenever feasible.

Example artifact:

```text
outputs/raw/activities.csv
```

---

# 8. Phase 2 — Prepare & Integrate

## 8.1 Goal

Convert raw activity and structure records into a consistent, machine-readable, analysis-ready molecular dataset.

---

## 8.2 Data-type normalization

Required numeric fields must be converted explicitly.

Invalid numeric conversion must not silently produce a valid-looking value.

Examples include:

```text
standard_value
```

and other selected quantitative fields.

Conversion failures must be logged or counted as exclusions.

---

## 8.3 Missing-value policy

The workflow must distinguish:

```text
required-field missingness
```

from:

```text
optional-field missingness
```

Rows should only be removed automatically when a field required for the current downstream task is missing.

For an IC50 structure-based dataset, required fields may include:

```text
molecule_chembl_id
standard_value
standard_units
standard_relation
canonical_smiles
```

Optional metadata should not cause record deletion merely because it is missing.

Every exclusion should be countable by reason.

---

# 9. Duplicate and Repeated-Measurement Policy

Duplicate handling must distinguish fundamentally different cases.

## 9.1 Exact duplicates

Rows that are identical across the relevant measurement fields may be removed automatically.

The number removed should be recorded.

---

## 9.2 Structure-table duplicates

When multiple structure records correspond to the same unique molecule identifier but contain equivalent structure information, one canonical structure record may be retained.

The molecule identifier is used as the primary join key unless implementation requirements indicate otherwise.

---

## 9.3 Repeated biological measurements

Multiple activity records associated with the same molecule are not automatically treated as duplicate data.

For example:

```text
CHEMBL_X   IC50 = 20 nM
CHEMBL_X   IC50 = 35 nM
CHEMBL_X   IC50 = 400 nM
```

may represent different:

* assays;
* experimental conditions;
* publications;
* constructs;
* biological systems.

Therefore the default behavior is:

```text
keep_all
```

Repeated measurements should remain separate unless the downstream task explicitly requires molecule-level aggregation.

---

## 9.4 Molecule-level aggregation

If the user explicitly requests one value per molecule, the Skill should identify the presence of repeated measurements before aggregation.

Potential strategies may include:

```text
keep_all
median
mean
best
assay-restricted aggregation
```

No aggregation strategy should be silently selected when it may materially affect interpretation.

For Version 0.1:

* `keep_all` is the default;
* molecule-level aggregation should require explicit user intent;
* the applied strategy must be recorded in the run metadata.

`best` must never be used merely as a convenience default because it systematically biases activity toward stronger measurements.

---

# 10. Structure Acquisition

The workflow extracts the unique molecule identifiers from the cleaned activity data and queries ChEMBL for associated molecular structures.

The structure dataset should contain at least:

```text
molecule_chembl_id
canonical_smiles
```

---

## 10.1 Structure validation

For each SMILES:

```python
Chem.MolFromSmiles(smiles)
```

or the corresponding RDKit operation should be used to validate parseability.

Records should be classified as:

```text
missing SMILES
invalid RDKit molecule
valid molecule
```

Invalid or missing structures cannot proceed to fingerprint generation.

The number excluded for each reason must be recorded.

---

# 11. Fingerprint Generation

Valid RDKit molecules should be converted into the molecular fingerprint required by the workflow.

The exact fingerprint algorithm and parameters must be explicit configuration rather than hidden implementation assumptions.

Configuration should record information such as:

```text
fingerprint_type
fingerprint_parameters
fingerprint_length, when applicable
```

The first implementation may reproduce the fingerprint strategy used in the reference TeachOpenCADD workflow.

The chosen representation and parameters must be written to run metadata so that downstream analyses are reproducible.

The physical storage format for fingerprints should be chosen during implementation.

Possible approaches include:

```text
serialized fingerprint column in the dataset
```

or:

```text
separate numeric fingerprint matrix
```

The decision should be documented once implemented.

---

# 12. Schema Normalization

Column names should be normalized before downstream analysis.

The normalized schema should:

* use stable names independent of API response formatting;
* distinguish raw from transformed values;
* avoid ambiguous units;
* support downstream code without repeated renaming.

For example:

```text
standard_value
standard_units
```

may later become an explicit normalized representation such as:

```text
activity_value
activity_unit
```

when appropriate.

Original values should be preserved whenever a transformation is irreversible or scientifically meaningful.

---

# 13. Activity–Structure Integration

The cleaned activity DataFrame and validated structure DataFrame are joined using:

```text
molecule_chembl_id
```

unless another identifier is explicitly required.

The merge must be validated.

The workflow should report:

* activity rows before merge;
* unique molecule IDs before merge;
* structure rows retrieved;
* structure rows retained;
* rows after merge;
* activity records lost because no valid structure was available.

---

# 14. Phase 3 — Interpret & Analyze

## 14.1 Goal

Interpret the property selected by the user, convert it into an appropriate numerical representation, summarize its distribution, and identify informative records.

---

# 15. Property Selection

The user should describe the analysis semantically rather than by DataFrame column name.

Example:

```text
Show me the compounds with the strongest EGFR inhibition.
```

The Agent may resolve this to something like:

```text
property = IC50
activity direction = lower value indicates stronger activity
```

When a transformed property is used:

```text
property = pIC50
activity direction = higher value indicates stronger activity
```

The mapping between natural-language intent and dataset property is an Agent responsibility.

The numerical implementation of the transformation is a deterministic-code responsibility.

---

# 16. Unit Standardization

Before comparing quantitative activity measurements, values must be expressed on a compatible scale.

The workflow must:

1. inspect existing units;
2. identify convertible records;
3. convert values to a chosen canonical unit;
4. exclude or separately flag unsupported units;
5. record all conversions.

For IC50, a convenient canonical representation is molar concentration or a consistently defined subunit such as nM before transformation.

---

# 17. IC50 to pIC50 Transformation

When requested or required for downstream analysis:

[
pIC_{50} = -\log_{10}(IC_{50}[\mathrm{M}])
]

For IC50 expressed in nM:

[
pIC_{50} = 9 - \log_{10}(IC_{50}[\mathrm{nM}])
]

The implementation must reject or flag:

```text
IC50 <= 0
```

before logarithmic transformation.

Known reference cases should be used in automated tests:

```text
1 nM     → pIC50 = 9
100 nM   → pIC50 = 7
1000 nM  → pIC50 = 6
```

---

# 18. Relation Operators and Censored Measurements

Activity measurements may use relations such as:

```text
=
<
>
<=
>=
```

These relations carry scientific meaning.

For example:

```text
IC50 < 100 nM
```

does not mean:

```text
IC50 = 100 nM
```

and therefore cannot be transformed into an exact pIC50 value without preserving the inequality.

For Version 0.1, exact quantitative datasets should default to:

```text
standard_relation == "="
```

Non-exact values should not be silently converted into exact values.

Excluded or separately retained censored records must be counted and reported.

Future versions may implement interval/censored-value handling explicitly.

---

# 19. Descriptive Statistics

Deterministic code should calculate statistics for the selected property.

At minimum:

```text
count
missing count
unique molecule count
mean
median
standard deviation
minimum
maximum
quartiles
```

Additional useful statistics may be added when justified by the data type.

---

# 20. Ranking and Extreme-value Inspection

The workflow should generate machine-readable subsets such as:

```text
top N
bottom N
```

using the correct scientific direction for the selected property.

Examples:

```text
IC50:
lower values = stronger activity

pIC50:
higher values = stronger activity
```

Sorting direction must therefore be defined by the property semantics and must not be guessed independently by the analysis script.

---

# 21. Agent-assisted Interpretation

The Agent should receive:

* summary statistics;
* top/bottom records;
* selected metadata columns;
* exclusion summary;
* relevant warnings.

The Agent may then identify potentially useful observations such as:

* high-value records concentrated in a particular assay type;
* extreme records associated with a specific publication;
* unexpectedly broad variation for repeated measurements;
* strong differences between assay contexts;
* potentially suspicious patterns worth manual inspection.

The Agent must distinguish:

```text
observed fact
```

from:

```text
possible interpretation
```

and must not make biological claims unsupported by the retrieved data.

---

# 22. Output Artifacts

A successful run should produce machine-readable and human-readable artifacts.

Proposed structure:

```text
outputs/
├── raw/
│   ├── activities.csv
│   └── structures.csv
│
├── prepared/
│   └── dataset.csv
│
├── statistics.json
├── exclusions.json
├── run_manifest.json
└── report.md
```

The exact file structure may be simplified during implementation if unnecessary.

---

# 23. Run Manifest

Each run should record sufficient information for reproducibility.

Possible fields include:

```text
target query
resolved target
target ChEMBL ID

activity property
activity filters

aggregation policy

unit conversion policy

fingerprint type
fingerprint parameters

raw activity count
final row count
unique molecule count

execution timestamp
software/package versions when practical
```

---

# 24. Exclusion Accounting

Every destructive filtering step should be observable.

A run should be able to produce an exclusion flow similar to:

```text
raw activity records
        ↓
wrong activity type
        ↓
non-exact relation
        ↓
missing required activity value
        ↓
unsupported unit
        ↓
missing structure
        ↓
invalid SMILES
        ↓
final dataset
```

Example machine-readable structure:

```json
{
  "raw_records": 0,
  "excluded": {
    "wrong_activity_type": 0,
    "non_exact_relation": 0,
    "missing_required_value": 0,
    "unsupported_unit": 0,
    "missing_smiles": 0,
    "invalid_smiles": 0
  },
  "final_records": 0
}
```

Counts must be computed from the actual pipeline rather than generated by the Agent.

---

# 25. Validation Invariants

A successful prepared dataset must satisfy explicit invariants.

Depending on the requested workflow, these may include:

```text
required columns exist

required fields contain no missing values

quantitative activity values are numeric

activity values used in logarithmic transforms are positive

normalized units are consistent

molecule IDs are present

SMILES are parseable by RDKit

fingerprints were generated successfully

fingerprint dimensions are consistent

merge keys are valid

reported row counts reconcile with pipeline operations
```

Validation failure should cause a clear failure state rather than silent continuation.

---

# 26. Failure Handling

The workflow should stop or request clarification in cases such as:

### Target resolution failure

```text
No suitable ChEMBL target found.
```

Action:

* show useful discovery information;
* request a better identifier or clarification.

### Ambiguous target

```text
Multiple plausible targets remain.
```

Action:

* present compact candidate information;
* ask user to select or clarify.

### Requested property unavailable

```text
No usable IC50 records exist for the resolved target.
```

Action:

* report available property types when possible;
* do not silently substitute another measurement.

### Unit incompatibility

```text
Activity records use unsupported or incompatible units.
```

Action:

* exclude or isolate affected records;
* report their count.

### Invalid structures

Action:

* exclude from structure-dependent outputs;
* report counts and identifiers when useful.

### Validation failure

Action:

* stop final delivery;
* identify the failed invariant;
* preserve intermediate artifacts where useful for debugging.

---

# 27. User Confirmation Policy

The Skill should minimize unnecessary questions.

User confirmation is required when a decision:

* changes the biological target;
* changes the property being analyzed;
* combines biologically distinct measurements;
* aggregates repeated measurements into one molecule-level value;
* introduces a scientifically consequential assumption.

User confirmation is not required for routine deterministic operations such as:

* numeric type conversion;
* removing exact duplicate rows;
* resetting DataFrame indexes;
* renaming columns according to the fixed schema;
* sorting;
* calculating descriptive statistics.

---

# 28. Logging and Transparency

The Skill should make significant decisions visible.

Important decisions include:

```text
resolved target
activity type selected
filters applied
records excluded
aggregation strategy
unit conversion
transformation
fingerprint configuration
```

The user should be able to understand how the final dataset was derived from the raw database response.

---

# 29. Proposed Implementation Boundaries

The first implementation may use:

```text
scripts/
├── discover_target.py
├── fetch_activities.py
├── prepare_dataset.py
└── analyze_dataset.py
```

### `discover_target.py`

Responsible for:

```text
identifier / query
→ ChEMBL target candidates
```

### `fetch_activities.py`

Responsible for:

```text
resolved target
+ selected activity filters
→ raw activity dataset
```

### `prepare_dataset.py`

Responsible for:

```text
activity data
+ molecule structure data
→ cleaned and integrated dataset
```

including:

* type conversion;
* missing-value handling;
* duplicate handling;
* structure retrieval;
* SMILES validation;
* fingerprint generation;
* schema normalization;
* merge.

### `analyze_dataset.py`

Responsible for:

```text
prepared dataset
+ selected property
→ transformed data
+ statistics
+ ranked records
```

The exact internal structure may be refactored after the first working implementation.

---

# 30. Acceptance Criteria for Version 0.1

Version 0.1 is considered functionally complete when all of the following are true:

1. A user can provide a target through natural language.
2. The Skill can resolve an appropriate ChEMBL target.
3. The Skill can retrieve the requested activity type.
4. The raw activity dataset is preserved.
5. Required activity fields are cleaned deterministically.
6. Repeated measurements are not silently collapsed.
7. Molecular structures are retrieved and validated.
8. Invalid or missing structures are handled explicitly.
9. RDKit fingerprints can be generated with recorded parameters.
10. Activity and structure datasets are merged reproducibly.
11. IC50 values can be standardized and converted to pIC50 correctly.
12. Descriptive statistics are generated by code.
13. High/low activity records are ranked with the correct direction.
14. Every filtering stage reports exclusion counts.
15. The final dataset passes defined validation checks.
16. The Agent can summarize the run without inventing information.
17. A fresh Codex session can use the Skill without requiring the user to understand ChEMBL API details or internal column names.

---

# 31. Initial Development Case

The first development case should reproduce and generalize the workflow learned from TeachOpenCADD T001.

The initial case should be used to verify:

```text
target resolution
→ activity retrieval
→ structure retrieval
→ cleaning
→ integration
→ activity transformation
→ fingerprint generation
→ statistics
```

After the initial target succeeds, at least one additional target should be used to verify that the implementation is not hard-coded to the reference example.

---

# 32. Future Extensions

Possible later extensions include:

* additional ChEMBL activity types such as Ki, Kd, and EC50;
* smarter assay-context comparison;
* configurable molecule-level aggregation;
* chemical standardization;
* scaffold analysis;
* multiple fingerprint types;
* export formats optimized for machine learning;
* automated visualization;
* QSAR-ready train/test splitting;
* additional public databases;
* Streamlit interface;
* richer provenance and reproducibility metadata.

These extensions should only be introduced after the Version 0.1 workflow is stable and validated.
