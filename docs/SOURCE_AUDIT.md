# Official source acquisition and preliminary feasibility audit

Audit date: **2 October 2026**. Outcome: **sources available; official analytical release remains blocked**. The analytical pipeline and static demo already exist. This audit does not replace the demonstration payload with official results.

## Acquired evidence

All **28 source snapshots** were downloaded, inspected and pinned by SHA-256 in [`sources.lock.yml`](../sources.lock.yml). The manifest records exact URLs, retrieval dates, explicit CSV encodings and delimiters, and reference-date evidence. Pins approve acquisition snapshots only. Raw files and unique receipts are retained locally under ignored `data/raw/`; the tracked [acquisition report](audit/acquisition.json) records sizes, hashes, final URLs, timestamps, response metadata and resource discovery. Raw bytes are excluded from Git.

The Madrid portal has migrated. The plan's legacy `200076-0-padron.xml` and `.csv` endpoints returned HTTP 404. The live catalogue links to a separate [historical dataset](https://datos.madrid.es/dataset/209163-0-padron-municipal-historico), whose [RDF resource catalogue](https://datos.madrid.es/dataset/209163-0-padron-municipal-historico.rdf) exposes January resources for every year from 2014 through 2025. Resource filenames have numeric identifiers that do not encode the year; the manifest uses catalogue descriptions rather than guessed filenames.

The downloaded [official content/structure PDF](https://datos.madrid.es/dataset/200076-0-padron/resource/200076-3-padron/download/200076-3-padron.pdf), version October 2019, explicitly states: “La fecha de referencia de cada fichero mensual de un mes genérico ‘m’ es el día 1 de dicho mes ‘m’.” January files therefore refer to 1 January. Recent files also contain reference-date and load-date columns; these are preserved separately in profiles. The PDF notes that EXT includes stateless people and people with nationality not recorded.

## Population profiles

The [machine-readable profiles](audit/padron_profiles.json) retain headers, age distributions, row counts, known count sums, blank-cell counts, geography inventories, conflicts and recent date values. Encoding varies between UTF-8 and Windows-1252. Field casing, quoting and whitespace also change between vintages.

| Reference date | Rows | Raw section codes | Sum of nonblank population counts | Blank count cells |
|---|---:|---:|---:|---:|
| 2014-01-01 | 232,074 | 2,417 | 3,176,508 | 296,007 |
| 2015-01-01 | 232,993 | 2,424 | 3,149,663 | 304,657 |
| 2016-01-01 | 233,469 | 2,420 | 3,174,945 | 302,903 |
| 2017-01-01 | 233,949 | 2,421 | 3,191,117 | 300,262 |
| 2018-01-01 | 236,337 | 2,443 | 3,231,062 | 297,248 |
| 2019-01-01 | 236,891 | 2,443 | 3,275,195 | 289,584 |
| 2020-01-01 | 237,581 | 2,443 | 3,345,894 | 280,036 |
| 2021-01-01 | 237,758 | 2,445 | 3,292,949 | 0 |
| 2022-01-01 | 238,221 | 2,445 | 3,296,033 | 279,395 |
| 2023-01-01 | 238,497 | 2,451 | 3,352,448 | 0 |
| 2024-01-01 | 239,074 | 2,451 | 3,473,648 | 0 |
| 2025-01-01 | 240,632 | 2,463 | 3,540,364 | 0 |

These are **raw known-count sums**, not independently reconciled official city totals. Blank cells are counted as unknown and excluded from the known sum, without treating them as observed zero. No inference about suppression or zero encoding has been approved.

Actionable schema findings:

- The 2015 file has one recorded age of 135, outside the existing analytical contract; preserve it in an exception table and obtain an explicit treatment.
- Starting in 2023, `100 o +` is an open age group. The 2025 endpoint contains 1,346 rows with this label. The pipeline currently expects integer ages; it needs a declared terminal-cohort policy before these sources can be normalised.
- Four exceptional 2015 section codes have no polygon: `2807901888`, `2807912999`, `2807915999`, `2807919999`, containing 12 known people in total. They must remain visible in reconciliation and exception accounting.
- The 2025 source includes `2807908130`, with three people, absent from the 2025 geometry archive, plus two people without section codes. All five remain in city accounting. The earlier profiler skipped uncoded rows; this is corrected in the follow-up report.
- Section `2807919036` has two barrio memberships in the 2025 source. At age 45 it has two separate rows: 14 people in barrio `1902` and one in barrio `1901`. This is a duplicate at section-age grain, not a byte-identical duplicate. Do not drop either row or choose a parent silently.
- Intermediate-year totals show changes that require administrative/revision checks, especially 2020–2021 and 2023–2024. A change in the raw sum alone does not identify its cause.

## Mortality coverage

The plan's `TABLA/27154?tip=AM` URL returns HTTP 200 with the text “La operación indicada no existe (TABLA)”, rather than JSON. The downloader rejects it. Working sources are the official CSV export and `SERIES_TABLA` metadata endpoint, now recorded in the manifest.

The [mortality report](audit/mortality.json) establishes:

- **Madrid regional table 27154:** annual observations cover the required 2015–2024 period, but ages are grouped: 0, 1–4, five-year groups and terminal groups. It does not supply the 2,000 sex/year/single-age cells needed at ages 0–99. Missing observations in redundant terminal categories are recorded separately. Grouped risks must not be passed to the existing single-age model.
- **Spain national table 27153:** all 2,000 male/female single-age risk cells at ages 0–99 across 2015–2024 are present, with an additional `100 y más años` terminal group. This is a viable source candidate if national mortality is explicitly adopted; it does not establish small-area mortality accuracy.
- Both metadata sets label `Riesgo de muerte` in **Tanto por mil**. If adopted, divide that measure by 1,000 to obtain `qx`. `Tasa de mortalidad` is a distinct measure and must not be substituted. CSV numeric parsing must account for decimal commas and period thousands separators.

The follow-up normalisation configures national single-age mortality with an explicit caveat and paired endpoint ages 10–99. Regional sensitivity remains pending. See [endpoint reconciliation](RECONCILIATION.md) for the implemented policy; grouped regional risks are not interpolated.

## Preliminary geographic feasibility

Both official archives downloaded successfully. Their layer names identify 1 January 2015 and 1 January 2025; both declare ETRS89 / UTM zone 30N, verified as EPSG:25830. The Madrid municipality contains **2,420** start-year and **2,462** endpoint polygons. No Madrid polygon is empty or invalid. The legacy GIS landing page in the original plan describes November 2011 cartography; it is not reference-date evidence for these archives.

The [spatial report](audit/boundaries.json) records every bipartite overlap component and its old/new codes, mutual overlap and symmetric-difference area. At the plan's provisional 99.9% mutual-overlap tolerance:

- 2,221 components are candidate unchanged sections with matching IDs.
- 122 components are candidate stable aggregates of changed sections. The largest contains 19 sections in one vintage.
- Candidate comparable components cover **99.9996%** of known 2015 counts and **99.9999%** of known 2025 counts. This exceeds the proposed 95% feasibility threshold provisionally; the denominator includes known counts only and does not resolve older blank cells.
- The whole-municipality symmetric difference is approximately 7.59 m². Aggregate internal overlap is negligible in 2015 and approximately 0.082 m² in 2025, subject to floating-point precision.

The graph excludes intersections at or below the larger of 1 m² and 0.1% of the smaller polygon area; excluded intersections total approximately 41.23 m². These settings and all candidate labels are explicit in the report. They are an audit heuristic, not approved population-allocation weights. No polygons were repaired, clipped or interpolated.

**The spatial gate remains open:** changed components and borderline differences need review; every ignored materiality choice must be acceptable; missing source codes need resolution; historical barrio/district geometries and parent containment still require independent verification. A high component coverage percentage does not approve current barrio boundaries or resolve the source's multiple-barrio section.

## Remaining production gates and next implementation

The [feasibility report](audit/feasibility.json) keeps `production_ready=false`. Independent INE and revised municipal totals are now acquired, differences are accounted for by section, and audit normalisation is implemented; see [the follow-up report](RECONCILIATION.md). The original production checklist remains:

1. Obtain independently published endpoint totals and reconcile differences, including blanks and exceptional codes. Then check barrio/district totals and intermediate-year administrative breaks.
2. Define versioned raw-schema aliases and explicitly approved blank, unknown-age and terminal-age rules. Retain exception rows and audit totals; resolve section/barrio membership without loss of counts.
3. Adopt and configure a documented mortality method and terminal-cohort treatment; validate selected survival chains and sensitivity to region.
4. Review changed spatial components and historical parent boundaries, then produce a versioned crosswalk with conservation checks and approved reliability labels.
5. Run the normalised official pipeline and full release QA. Replace the demo only after those gates pass.

## Reproduce

Use the commands in [`README.md`](../README.md#official-source-audit). The acquisition step fails on checksum drift, invalid payloads, truncation, oversized downloads or HTTP/network errors. Each attempt retains a unique receipt. Metadata snapshots can change independently of data; inspect changes before updating a pin. The report builder verifies stored bytes against both receipts and manifest pins. The population profiler preserves uncertainty rather than repairing source semantics.

The spatial audit's optional dependencies are pinned in `pyproject.toml`; analysis and acquisition remain standard-library Python. The executed GIS environment used Python 3.12, Shapely 2.1.2, pyshp 2.3.1, pyproj 3.7.2 and NumPy 2.3.5. Synthetic checks cover exact splits, renumbering and same-ID redraws; acquisition checks cover checksum drift, immutable repeated retrieval, size limits, truncation, malformed responses and network failure.
