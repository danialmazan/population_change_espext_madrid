# Endpoint reconciliation and normalisation

Completed 2 October 2026. Independent comparisons and audit normalisation are implemented. **Official analysis remains gated**: the source series differ, baseline blanks remain unknown, and the geographic crosswalk requires review.

## Independent published counts

The downloader acquired and pinned INE [table 2881](https://www.ine.es/jaxiT3/Tabla.htm?t=2881), Madrid's municipal methodology, and two historical section/nationality workbooks from the municipal [bank of data](https://servpub.madrid.es/CSEBD_WBINTER/arbol.html). The bank tree supplies series IDs `0302010300061` (2009–2019) and `0302010300062` (2020–2026). The workbook sheet labels and titles explicitly identify the revised padrón at 1 January of each endpoint year.

| Reference date | Monthly raw known-count sum | Annual revised municipal total | INE legal total | Monthly minus municipal revised | Monthly minus INE |
|---|---:|---:|---:|---:|---:|
| 2015-01-01 | 3,149,663 | 3,141,991 | 3,141,991 | 7,672 | 7,672 |
| 2025-01-01 | 3,540,364 | 3,527,924 | 3,506,730 | 12,440 | 33,634 |

Madrid's methodology says the municipal statistical exploitation is exhaustive but its counts do not have the legal status of the INE figures and can differ from them. The monthly files and annual revised workbooks also differ. These statements identify distinct series; they do not establish the cause of each individual difference. **No counts are rescaled or overwritten to force agreement.**

The [reconciliation report](audit/reconciliation.json) retains both comparisons by sex, the revised four-category counts, every differing published section total, unmatched codes and source hashes. Published section totals sum exactly to the revised city totals. Differences across sections, raw-only geography and uncoded residents sum exactly to the city discrepancy. The 2015 workbook differs from the monthly extract in 2,222 of its 2,420 sections; the 2025 workbook differs in 2,331 of 2,462. This is a broad revision difference, not an isolated missing section. The precise revision process and the choice of analytical source series still need to be settled.

The municipal workbooks have a separate **No consta** nationality group: 16 people in 2015 and 139 in 2025. Including this group closes the published identity `Spanish + foreign + No consta = total`, including the sex totals. For comparisons against raw EXT, foreign and No consta are combined because the raw-source documentation explicitly includes unknown nationality in EXT. This category mapping is recorded; the report does not equate raw EXT with the workbook's foreign-only column.

## Correction to the preliminary profiler

The initial profiler skipped rows with invalid geography before summing counts. Normalisation exposed two uncoded-section rows in 2025, containing two people in district 06, barrio 0606, at ages 42 and 50. Those rows are now retained in the city counts and flagged as missing geography. The corrected raw 2025 total is **3,540,364**, two above the earlier preliminary number. Five people in uncoded 2024 rows are also retained, correcting that known-count sum to **3,473,648**. Profiles and geographic population coverage were regenerated.

No artificial section code is assigned. The 2025 endpoint has five known people without a matching polygon: two without section codes and three in `2807908130`, absent from the geometry archive. The 2015 endpoint has twelve known people in exceptional codes without polygons. Synthetic tests now ensure an invalid geography cannot silently remove population from the audit sum.

## Explicit input contracts

[`config/schema_aliases.json`](../config/schema_aliases.json) pins exact column aliases, encodings and delimiters for both endpoint files. Unexpected headers, negative counts, duplicate full-grain source rows, inconsistent codes and mismatched embedded reference dates fail normalisation.

The generated long-form records preserve reference date, vintage section code, district, barrio, age label and kind, sex, nationality, nullable population, cohort eligibility, geometry presence, source hash, schema version and raw row number. The full grain includes barrio membership. The two age-45 rows for section `2807919036` remain separate rather than being dropped or assigned one parent.

The [normalisation report](audit/normalisation.json) verifies:

- 2015: 931,972 long-form cells; 3,149,663 known people conserved; all 304,657 blank count cells retained as unknown.
- 2025: 962,528 long-form cells; 3,540,364 known people conserved; no blank count cells.
- Invalid ages, open terminal groups, births during the interval, missing geometry and split barrio membership remain visible rather than disappearing during conversion.

An empty population field means **unknown**, not zero. These audit records deliberately do not fit the production model's non-null, harmonised input contract. They cannot be used as official model inputs until that contract is satisfied.

## Mortality and terminal ages

[`config/analysis.json`](../config/analysis.json) adopts Spain's national annual single-age mortality from table 27153, with an explicit caveat that national period tables are not Madrid-specific. The normaliser verifies source metadata units and complete coverage, then exports all **2,000 male/female age/year probabilities** at ages 0–99 for 2015–2024. It uses `Riesgo de muerte / 1000`; it never substitutes the death-rate measure or expands the open terminal group.

The paired counterfactual covers **endpoint ages 10–99**, corresponding to baseline ages 0–89. Baseline ages 90+ and endpoint ages 100+ are retained as separate observed/excluded records. This avoids assigning invented single ages to `100 o +` or projecting into an unsupported terminal-age mortality schedule. The anomalous baseline age 135 remains an exception. Endpoint ages 0–9 remain observed-only.

Known population partitions reconcile to the full known sums:

| Endpoint file | Eligible cohort known count | Observed births during interval | Terminal-age known count excluded | Invalid-age known count excluded |
|---|---:|---:|---:|---:|
| 2015 baseline | 3,109,701 | — | 39,961 | 1 |
| 2025 endpoint | 3,275,658 | 262,476 | 2,230 | 0 |

Regional mortality sensitivity remains pending. This narrower age scope is explicit in the configuration and must accompany any eventual results.

## Reproduce and remaining release work

After acquiring the pinned sources and generating profiles/boundaries, run:

```bash
PYTHONPATH=src python -m madrid_demography.reconcile
PYTHONPATH=src python -m madrid_demography.normalise
PYTHONPATH=src python -m madrid_demography.audit
```

The XLSX reader uses the Python standard library and reads stored workbook values, not recalculated formulas. Normalisation verifies pinned raw hashes and conserves both known counts and unknown cells. Generated CSVs stay under ignored `data/normalised/`; tracked reports contain their hashes. Production remains blocked until a compatible monthly/revised source policy and blank-count rule are supported by evidence, geographic components and historical parent boundaries are reviewed, and release QA passes. The demonstration website remains unchanged.
