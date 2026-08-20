# ChEMBL pIC50 dataset contract

## API calls

- `GET https://www.ebi.ac.uk/chembl/api/data/target/search.json?q=<query>` resolves human-readable target queries.
- `GET https://www.ebi.ac.uk/chembl/api/data/activity.json?target_chembl_id=<id>&standard_type=IC50` retrieves paginated activity records.
- `GET https://www.ebi.ac.uk/chembl/api/data/molecule/<molecule_chembl_id>.json` supplies a canonical SMILES only when the activity payload lacks one.

The pipeline follows `page_meta.next` until all activity pages are collected.

## Inclusion and exclusion order

Each rejected record receives the first applicable reason below, so counts are mutually exclusive.

1. Missing `molecule_chembl_id`, `standard_value`, or `standard_units`.
2. `standard_type` is not `IC50`.
3. `standard_relation` is not `=`.
4. ChEMBL provides a non-empty `data_validity_comment`.
5. `standard_value` is non-numeric or not positive.
6. `standard_units` is outside `pM`, `nM`, `uM`, or `mM`.
7. No canonical SMILES is available after the molecule lookup.
8. RDKit cannot parse the canonical SMILES.

Conversions to nM are `pM × 0.001`, `nM × 1`, `uM × 1,000`, and `mM × 1,000,000`. The pIC50 formula is `9 - log10(IC50_nM)`.

## Outputs

`dataset.csv` has one accepted ChEMBL activity per row and contains identifiers, the original standardized measurement, `ic50_nM`, `pIC50`, `canonical_smiles`, and a 2048-bit Morgan fingerprint (`radius=2`) as a bit string. Rows are sorted by descending pIC50, then activity ID.

`statistics.json` records source counts, mutually exclusive exclusion counts, the pIC50 summary, and fingerprint settings.
