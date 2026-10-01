# Madrid demographic counterfactual, 2015–2025: implementation plan

**Status:** core software implemented and fixture/browser checks passing; core pipeline, explorer, QA/export, and research scenario APIs implemented. Official source acquisition, empirical audits, release gates, and conditional research validation remain incomplete. See [implementation status](docs/IMPLEMENTATION.md).
**Headline comparison:** 1 January 2015 to 1 January 2025 (subject to the source audit below).  
**Recommended public term:** **observed-minus-expected population residual**. In short UI labels use **demographic residual**; describe the combined Spanish + foreign result, cautiously, as a **net residential-change proxy after mortality**. Never call it observed migration.

## 1. Go/no-go conclusion

The project is statistically defensible if it is framed as a cohort accounting counterfactual, not a migration-flow estimate. It is geographically defensible only after a reproducible boundary audit. The launch gates are:

1. January 2015 and January 2025 files use compatible reference dates and can be reconciled to published Madrid totals.
2. Every section is assigned a boundary status and all non-identical sections are aggregated to a common stable zone or excluded; interpolation must not be invisible.
3. Annual, age- and sex-specific official survival probabilities cover every cohort used.
4. Ages 0–9 are excluded from the V1 cohort residual and labelled “born during the comparison period”.
5. The public presentation leads with the combined ESP+EXT residual. Nationality-specific residuals are secondary because they contain nationality switching.

If exact stable zones leave too few recognisable census sections, the MVP should publish barrio and distrito results first and expose section results only where `boundary_method` is `unchanged` or `exact_aggregate`.

## 2. Authoritative source register and acquisition audit

This register identifies the exact source datasets and URLs to resolve and pin before implementation.

The URLs below are the canonical landing pages, machine endpoints, or documented download patterns to pin in a versioned source manifest. A source URL is not evidence that two releases are comparable: the first pipeline milestone is to download, checksum and profile each file. The research environment used to prepare this plan returned HTTP 401/403 for external browsing, so values marked **confirm before build** are deliberately not represented as verified observations. The pipeline must fail closed until those checks are complete.

### 2.1 Madrid padrón

| Source | Exact URL | Intended use | Required fields | Availability / verification |
|---|---|---|---|---|
| Ayuntamiento open-data dataset, “Padrón Municipal de Habitantes. Explotación estadística” | <https://datos.madrid.es/sites/v/index.jsp?vgnextoid=1d755cde99be2410VgnVCM1000000b205a0aRCRD> | Dataset documentation, update frequency, licence and resource list | title, description, coverage, update timestamp, resource URLs | Canonical catalogue record; confirm that the historical resource still begins in 2014 and records are monthly. |
| Catalogue metadata | <https://datos.madrid.es/egob/catalogo/200076-0-padron.xml> | Machine-discover the current resources rather than guessing filenames | resource URL, format, byte size, modified date | Parse on every acquisition; archive the XML beside raw data. |
| Published CSV endpoint | <https://datos.madrid.es/egob/catalogo/200076-0-padron.csv> | Candidate detailed padrón resource | `COD_DISTRITO`, `COD_DIST_BARRIO`, `COD_DIST_SECCION`, `COD_EDAD_INT`, four sex × nationality counts | Confirm whether this endpoint is current-only or historical, and whether the resource list exposes monthly archives. Never overwrite prior downloads. |

Expected count columns from the published description/sample convention are `EspanolesHombres`, `EspanolesMujeres`, `ExtranjerosHombres`, and `ExtranjerosMujeres` (accents/case/abbreviations may vary). Treat these as aliases, not a promised schema. The audit must record, for every monthly file:

- exact filename/URL, SHA-256, bytes, encoding, delimiter, decimal convention, header text and row count;
- reference month/date and whether it describes population at the start or end of month;
- distinct ages, minimum/maximum age and any `100+`, blank, unknown or total rows;
- geography padding and type (`01` versus `1`, section code local versus full INE code);
- count-column names/types, suppressed/null/negative values and duplicate keys;
- documented revisions, breaks or retrospective corrections.

Use `charset-normalizer` only to diagnose; set the chosen encoding explicitly after inspection (likely Windows-1252/ISO-8859-1 for older exports or UTF-8 for newer ones). Preserve raw header bytes. Build a versioned alias map such as `schema_version`, `source_column`, `canonical_column`, `valid_from`, `valid_to`; do not scatter rename logic through transformations.

**Reference-date rule:** prefer releases explicitly labelled **1 January 2015** and **1 January 2025**. If files are labelled only by month, establish semantics from metadata and totals. Do not compare December 2014 month-end to January 2025 month-end and call it exactly ten years. Store `reference_date`, `release_date`, and `interval_years` separately.

### 2.2 Mortality and survival

| Source | Exact URL | Intended use | Required dimensions / measures | Availability |
|---|---|---|---|---|
| INE table 27154, mortality tables | <https://www.ine.es/jaxiT3/Tabla.htm?t=27154> | Official annual life-table functions | year, autonomous community, sex, exact age; `q_x` or `p_x`/survivors | Confirm table dimensions and latest year through metadata. Use Comunidad de Madrid if complete for 2015–2024. |
| INE JSON table endpoint | <https://servicios.ine.es/wstempus/js/ES/TABLA/27154?tip=AM> | Machine metadata/data discovery | variable IDs, value IDs, units, notes, update date | Pin returned metadata and construct explicit filtered queries; do not depend on default ordering. |
| INEbase mortality collection | <https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736177004&menu=resultados&idp=1254735573002> | Definitions and methodological notes | definition of age, period table, `q_x`, territorial coverage, revisions | Authoritative methodology fallback and provenance. |

Preferred measure is `q_x`, the probability of dying between exact ages `x` and `x+1`, with `p_x = 1-q_x`. If only `l_x` is available, calculate `p_x=l_{x+1}/l_x`; if only age-specific death rates `m_x` exist, do **not** substitute `1-m_x` without a documented life-table conversion. Prefer Comunidad de Madrid over Spain. Use province only if INE publishes a methodologically equivalent annual single-age series with sufficient stability; smaller-area estimates can be noisy.

Annual 2024 probabilities are required for the final 2024→2025 transition. If they were not published at the extraction freeze, predeclare one fallback: use the latest official 2022–2023 or 2023–2024 multi-year table for that transition, publish a sensitivity run, and label it. Do not silently extrapolate.

### 2.3 Fertility (post-MVP research)

| Source | Exact URL | Intended use | Required dimensions | Availability |
|---|---|---|---|---|
| INE Basic Demographic Indicators, fertility | <https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736177003&menu=resultados&idp=1254735573002> | Annual age-specific fertility rates | year, Comunidad/province, age of mother (single year preferred), rate denominator/unit | Regional annual series generally available; confirm exact table ID and whether age is single-year or grouped. |
| INE Birth Statistics | <https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736177007&menu=resultados&idp=1254735573002> | Birth counts and nationality/country-of-birth evidence | year, mother’s age, mother’s nationality, child nationality if defined, territory | Cross-classification and confidentiality may limit provincial detail; confirm before any nationality-at-birth model. |

Rates must be converted using their documented units (commonly births per 1,000 women). Mother’s nationality is not the newborn’s nationality. No newborn ESP/EXT allocation should be inferred from it without a defensible civil-registration rule and validation.

### 2.4 Acquisitions of Spanish nationality (optional research)

| Source | Exact URL | Intended use | Required dimensions | Availability |
|---|---|---|---|---|
| INE, Statistics on Acquisitions of Spanish Nationality by Residents | <https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736177001&menu=resultados&idp=1254735573002> | Estimate broad age/sex/year naturalisation totals | year, province/CCAA, sex, age or age group, previous nationality, country of birth where available | Annual since 2013 at useful aggregate levels; exact cross-tab and territorial detail must be confirmed. Not section-level. |

The source counts acquisitions, not all nationality reclassifications in the padrón, and residence at acquisition does not establish residence throughout the interval. It can support sensitivity analysis, not an observed small-area correction.

### 2.5 GIS, identifiers and ancillary allocation data

| Source | Exact URL | Intended use | Required fields | Availability / caveat |
|---|---|---|---|---|
| INE census-section cartography landing page | <https://www.ine.es/censos2011_datos/cen11_datos_resultados_seccen.htm> | Documentation and official annual section downloads | province, municipality, district, section codes; geometry; reference year | Discover the appropriate annual products and licence here. |
| INE 2015 section archive (published filename pattern) | <https://www.ine.es/prodyser/cartografia/seccionado_2015.zip> | Start-year geometry | full section code and polygons | **Confirm before build:** URL pattern, CRS, layer names and whether release reflects 1 January boundaries. |
| INE 2025 section archive (published filename pattern) | <https://www.ine.es/prodyser/cartografia/seccionado_2025.zip> | End-year geometry | full section code and polygons | **Confirm before build:** 2025 archive availability and boundary reference date. |
| Madrid open-data catalogue | <https://datos.madrid.es/portal/site/egob> | Find official section, barrio and distrito layers and historical versions | codes, names, validity date, geometry | Catalogue searches must capture direct resource URLs in `sources.lock.yml`; do not use a current boundary for 2015 by assumption. |
| Madrid statistical portal | <https://www.madrid.es/portales/munimadrid/es/Inicio/El-Ayuntamiento/Estadistica/> | Official totals, territorial changes and administrative notes | published totals, nomenclátor/codes, change notes | Validation/reference source. |
| Spanish Cadastre INSPIRE downloads | <https://www.catastro.hacienda.gob.es/webinspire/index.html> | Possible dasymetric ancillary data | building geometry/use, residential area where licensed and temporally suitable | Use only after temporal coverage/licence/quality assessment; current buildings can bias 2015 allocation. |

Do not assume an official section correspondence table exists for the full interval. Search INE and Madrid metadata for change tables first; geometry overlay plus stable IDs is still required to verify them.

## 3. Canonical data model

### 3.1 Normalised padrón fact

One row per:

`reference_date, source_geography_id, age, sex, nationality_group`

with:

- `population` (non-negative integer);
- source provenance (`source_file_id`, `schema_version`, `raw_row_number`);
- source hierarchy codes (`district_code`, `barrio_code`, `section_code`);
- canonical INE section ID, normally province + municipality + district + section, stored as text with leading zeros;
- flags for totals/unknown ages (excluded from analytic facts but retained in an audit table).

Unpivot the four population columns into `sex ∈ {male,female}` and `nationality_group ∈ {ESP,EXT}`. A unique constraint covers all five dimensions. Counts remain integers until geographic allocation creates fractional estimates.

### 3.2 Geometry and crosswalk tables

`geometry_version(year, source, geography_level, source_id, geometry, crs, valid_date, checksum)`

`common_zone(zone_version, zone_id, display_level, geometry, quality_status, method, notes)`

`geography_crosswalk(zone_version, source_year, source_id, zone_id, weight, weight_basis, overlap_area, diagnostics)`

`quality_status ∈ {unchanged, exact_harmonisation, estimated_harmonisation, unreliable}`. The weights for every source polygon must sum to 1 within tolerance or the build fails. Exact aggregation uses only weights 0/1. Estimated weights carry uncertainty and never masquerade as observed counts.

## 4. Geographic comparability workflow

Use ETRS89 / UTM zone 30N (EPSG:25830) for topology/area operations; serve WGS84 or Web Mercator derivatives only after analysis.

1. **Clean and validate:** repair only documented invalid polygons; retain originals; check CRS, empty/multipart geometry, self-intersections, gaps and overlaps; clip both years to the same municipal boundary only for diagnostics, not to hide changes.
2. **Canonicalise IDs:** compare padded official codes and parent hierarchy. Separately distinguish ID equality from geometric equality.
3. **Overlay 2015 and 2025:** calculate intersection area and symmetric-difference ratios. Use a strict tolerance appropriate to source precision (provisionally ≥99.9% mutual overlap and negligible symmetric difference), then visually audit borderline cases.
4. **Classify graph components:** create a bipartite graph linking polygons with material overlap. A 1:1 component is unchanged or redrawn/renumbered; N:1 and 1:N may allow exact aggregation; N:M is a candidate common zone or estimation.
5. **Prefer common stable zones:** dissolve all connected old/new polygons in a changed component into the smallest identical union that covers both vintages. A zone may be larger than a 2025 section but preserves physical comparability without inventing population.
6. **Verify parents independently:** overlay historical barrio and distrito boundaries. Aggregate stable zones only when wholly nested in a common parent. Where a parent changed, publish a harmonised parent or flag it. Never infer historical membership solely from the current code.
7. **Estimate only as an optional tier:** if an analytically important component cannot form a useful exact zone, use address/building residential capacity or gridded/building-level population appropriate to each reference year. Compute weights by inhabited residential space, not bare land. Report `weight_basis`, effective population affected and sensitivity against area weighting.
8. **Exclude failures:** zones with severe topology defects, absent source rows, incompatible dates or high allocation sensitivity receive `unreliable` and are suppressed from ranking/default maps.

The boundary audit deliverable must list every section as unchanged, renumbered but geometrically equivalent, split, merged, materially redrawn, missing, or extra, plus population and land area in each category. “Exactly which sections changed” cannot responsibly be asserted until the two official archives are acquired and overlaid; it is a required, version-controlled output rather than a manual note in this plan.

## 5. Cohort and survival methodology

Let `P[g,a,s,n,t0]` be the start population in harmonised geography `g`, exact age `a`, sex `s`, nationality group `n`, at `t0`. Let `q[x,s,y,r]` be the official period-table probability of death before exact age `x+1` for region `r` in year `y`.

For integer dates separated by `k` years:

```text
p[x,s,y] = 1 - q[x,s,y]
S[a,s,t0→t1] = product over j=0..k-1 of p[a+j,s,year(t0)+j]
Expected[g,a+k,s,n,t1] = P[g,a,s,n,t0] × S[a,s,t0→t1]
Residual[g,a+k,s,n] = Actual[g,a+k,s,n,t1] - Expected[g,a+k,s,n,t1]
Residual_total = Residual_ESP + Residual_EXT
Residual_rate = Residual_total / Expected_total
```

Calculate at sex level and sum sexes only afterward. Apply the same sex-specific survival schedule to ESP and EXT in V1: suitable annual single-age, Madrid-level mortality by this binary nationality grouping is unlikely to be robust, and applying different national schedules would confound composition and selection. State that explicitly. Add national-origin-specific mortality only after evidence and sensitivity testing.

### Important timing qualification

“Age 25 on 1 January 2015” is not one exact-birthday cohort: it contains birth dates throughout a year. Mapping it to age 35 on 1 January 2025 is valid for completed-age cells over an integer interval, but period-table application at exact ages is an approximation. Preferred V1 calculation uses the annual `p_x` chain above; test a half-age/interpolated exposure variant at city level. If material (predeclare >0.5% for a broad age group or visibly relevant at old ages), publish it as a sensitivity range.

### Very old ages

- Inspect padrón top-coding before deciding the maximum analytic age.
- For exact ages available in both padrón and life table, calculate normally.
- For an open `100+`/`105+` source group, do not pretend to shift individuals by exact age. Aggregate both observed and expected into a compatible terminal band and propagate it with the life table’s open-interval method, or suppress the residual if no defensible method exists.
- Avoid section-level single-age charts at extreme ages where expected counts are tiny. Default to `85+` or another empirically chosen terminal band and show counts/uncertainty warnings.

### Aggregation and rates

Sum expected and actual counts first, then calculate residuals/rates. Never average section rates to produce a barrio result. Alongside `residual / expected`, publish residual per 1,000 expected residents and absolute observed change. Suppress/grey rates with very small denominators (threshold chosen after distribution inspection), while retaining additive counts.

## 6. Ages 0–9 and births

**Recommendation: defer the birth counterfactual from V1.** In 2025, ages 0–9 have no baseline cohort. Show their observed count/distribution in a separate panel labelled “born during 2015–2025; no cohort counterfactual”, and exclude them from headline residual totals and rankings. Provide an explicit toggle only if users might otherwise assume “all ages”.

Reasons:

- birth occurrence depends on women who themselves enter/leave after 2015, making “births if the original population stayed” sensitive to a second-order counterfactual;
- regional fertility rates cannot capture small-area fertility composition;
- mother’s nationality is not a robust assignment of newborn nationality;
- infant/child mortality, maternal cohort survival and births’ timing add model dependencies disproportionate to V1 value.

For a later **total-population-only** extension, age the baseline female population annually, apply official age/year-specific fertility rates (`ASFR/1,000 × mid-year women`), distribute births through each year under a stated timing assumption, apply sex ratio at birth and child survival, and advance newborn cohorts to the endpoint. Present nationality descriptively, not counterfactually, unless legal/statistical data directly support assignment. Compare projected births with observed Madrid births as a model validation, not calibration hidden from users.

## 7. Nationality changes

### V1 recommendation

Do **not** adjust section-level ESP/EXT residuals in the primary results. Lead with combined ESP+EXT, where a within-area EXT→ESP reclassification cancels algebraically (apart from survival-model and timing differences). Show raw ESP and EXT as compositional diagnostics with a prominent naturalisation caveat.

### Optional research layer

If the INE acquisition data have age/sex/year detail, construct `N[a,s,y]` for Madrid province or region, reconcile the geography to Madrid municipality where possible, and allocate only as an explicitly modelled scenario:

```text
r[a,s,y] = acquisitions[a,s,y] / foreign_population_at_risk[a,s,y]
allocated_N[g,a,s,y] = foreign_at_risk[g,a,s,y] × r[a,s,y]
adjusted_residual_ESP = raw_residual_ESP - cumulative_allocated_N_surviving_to_2025
adjusted_residual_EXT = raw_residual_EXT + cumulative_allocated_N_surviving_to_2025
```

Cap impossible hazards, advance age annually, and remove estimated acquisitions from subsequent foreign exposure. Improve allocation only if origin composition exists at matching small-area/age detail. Provide low/base/high allocation scenarios and retain exact cancellation in the total. Implement publicly only if it materially reduces opposite-signed ESP/EXT residuals in validation areas while remaining stable under allocation variants. Otherwise it adds false precision and belongs in a research appendix.

## 8. Pipeline and reproducibility

Use a static, offline build. Python with DuckDB + Polars/PyArrow for tabular work and GeoPandas/Shapely (or DuckDB Spatial) for GIS is a pragmatic recommendation; package versions and the environment must be locked.

```text
sources.lock.yml
  ↓ acquire (immutable files, metadata, checksums)
data/raw/{padron,ine_mortality,gis,...}
  ↓ profile + schema contracts
data/intermediate/padron_normalised.parquet
data/intermediate/geometries_*.parquet
  ↓ overlay + reviewed crosswalk
data/intermediate/common_zones.parquet
  ↓ apply exact/estimated weights
data/intermediate/population_harmonised.parquet
  ↓ survival matrix + cohort model
data/derived/cohort_detail.parquet
  ↓ additive aggregation + indicators
data/derived/{section_zone,barrio,distrito,city}_summary.parquet
  ↓ web export, validation, content hashing
public/data/manifest.json + TopoJSON + partitioned profile files
```

Every stage writes provenance, row counts and QA results. Keep raw data out of Git if licensing/size dictates; commit manifests, schemas, transformations, small fixtures and checksums. CI should use fixtures; a scheduled/release job with source access performs the full reproducible build. Parameterise `start_date`, `end_date`, mortality region, terminal age and `zone_version`; require an integer number of years for the initial model.

### Proposed analytical outputs

1. **`area_index`** (one row per area/level): `area_id`, name, parent IDs, level, geometry key, centroid, boundary status/method, affected share, reliability note.
2. **`profile`** (area × endpoint age × sex or sex-total × nationality): baseline at age `a-k`, baseline aged without mortality, expected after mortality, actual, residual, residual total, denominator flags.
3. **`age_band_summary`** (area × band × nationality): additive versions of the above plus rates/shares.
4. **`map_indicator`** (area × indicator × age-band): precomputed value, numerator, denominator, suppression and quality flags.
5. **`composition`** (area × year × age/band): ESP, EXT, total and shares.
6. **`method_metadata`**: dates, source hashes, survival version, zone version, formulas, build commit and QA report URL.

Parquet is the canonical analytical format, not necessarily browser payload. Use integer/fixed-width types where safe and dictionary encoding for categories.

## 9. Web delivery and performance

The repository contains no existing web stack yet, so the interface contract should remain framework-neutral. Once a stack exists, favour a static application/CDN rather than a live analytical database:

- one simplified **TopoJSON** file per spatial level, with stable `area_id` only; quantise/simplify display geometry but retain unsimplified analysis geometry offline;
- a small compressed **JSON index** and precomputed map-indicator files for initial rendering;
- profile payloads partitioned by level and a deterministic prefix/hash (or one compressed file per barrio/distrito and section chunks), fetched only on selection;
- optional **Arrow IPC/Parquet** only if the chosen browser stack already supports it efficiently; JSON is simpler for small pre-aggregated profiles;
- content-hashed URLs, immutable caching, a manifest that binds data and geometry versions, lazy chart modules and request cancellation on rapid selection.

Precompute all survival chains, residuals, age bands, denominators, ranks and standard indicators during the build. Browser work should be filtering and presentation, not cohort modelling. Budget after real-data profiling: target <500 KB compressed initial data (excluding basemap), <1 MB compressed geometry per initial level, and <100 KB typical area profile; revise simplification/partitioning based on measured payloads rather than arbitrary row limits.

## 10. Visual and information architecture

### 10.1 Page flow

1. **Intro / question.** “What would Madrid’s neighbourhoods look like today if their 2015 residents had simply aged in place?” Immediately distinguish observed, counterfactual and residual; state that under-10s are separate.
2. **Map.** Level switcher (comparable section zone, barrio, distrito), indicator, age range and count/rate toggle. Default to combined total residual per 1,000 expected, not raw count. Overlay/hatch estimated zones; grey unreliable zones.
3. **Area profile.** Headline actual/expected/residual cards; combined residual first; age residual chart; expected/actual distribution; nationality composition; boundary-reliability panel with method.
4. **City-wide explorer.** Distribution rather than only top/bottom league tables; allow age range and reliability filters; expose expected denominators so tiny areas do not dominate rankings.
5. **Methodology/data.** Formula walkthrough, source/version manifest, births exclusion, mortality assumptions, GIS crosswalk, naturalisation caveat, downloads and QA report.

### 10.2 Charts

- **Single-age residual:** diverging bars for raw ESP/EXT with a high-contrast point/line for combined total. Tooltips give actual, expected, residual and quality. Provide 5-year smoothing/bands for legibility but never discard underlying ages.
- **Expected versus actual:** recommend two small-multiple population pyramids (baseline aged without mortality → expected after mortality → actual) or an actual/expected line chart with a separate residual panel. Four overlapping lines are too cluttered. Keep the baseline on its 2015 age axis only when clearly shifted/aligned.
- **Composition:** 100% stacked ESP/EXT bars for 2015 and 2025, default five-year bands; display counts because percentages can magnify small denominators.
- **Maps:** sequential/diverging, colour-blind-safe scales centred at zero for residuals; use a robust symmetric domain while identifying clipped outliers. Counts are available but rates are default. Never use foreign-share change as a proxy for entries.
- **Reliability:** persistent badge and map layer, not tooltip-only disclosure. Downloaded records carry the same flags.

Age presets should be data-configured, not embedded in chart code. Start with `10–17`, `18–24`, `25–34`, `35–44`, `45–54`, `55–64`, `65–74`, `75+`, plus standard five-year bands. Keep `0–9` as an observed-only preset. Reconsider the terminal group and sparse young bands after inspecting distributions. Always permit a custom contiguous age range.

Accessibility requirements include keyboard-operable controls, non-colour sign encodings, textual chart summaries, locale-aware numbers, sufficient contrast and a table/download equivalent.

## 11. QA and validation contract

### Ingestion

- checksums and content-length changes are reviewed, not automatically accepted;
- schema alias coverage is complete; unexpected columns/ages fail the build;
- unique `date × geography × age × sex × nationality` keys;
- population is integer, non-negative and non-null; no impossible ages;
- all hierarchy codes are padded strings and map to exactly one parent for that vintage;
- source totals/unknown-age rows are reconciled rather than double counted.

### Arithmetic and hierarchy

- four raw sex/nationality cells equal the reconstructed row total;
- ESP + EXT equals total; male + female equals total;
- section sums match independently published barrio/distrito/city totals for each endpoint, with a documented tolerance and discrepancy table;
- exact-crosswalk weights are binary; all weight sums equal one; no population is created/lost on harmonisation;
- stable-zone → barrio → distrito → city actual, expected and residual counts are additive to floating-point tolerance;
- `Residual_total == Residual_ESP + Residual_EXT` at every additive grain;
- expected with survival is never greater than baseline for a cohort; survival is in `[0,1]` and weakly decreases over additional years.

### Geography

- every population section has a geometry and vice versa, with explicit exceptions;
- geometry validity, gaps/overlaps, area and parent containment are checked by vintage;
- boundary classifications are reproducible from overlap metrics and manually reviewed for all changed components;
- report number/share of sections, population and output zones by each quality class;
- compare exact-zone counts before/after crosswalk and run allocation sensitivity for estimated zones;
- validate simplified web geometry IDs against analytical IDs.

### Model validation

- independently reproduce selected survival chains from INE `l_x`/`q_x`;
- reconcile summed expected survivors and residuals at city level by age/sex;
- compare total residual with `actual endpoint - baseline - modelled deaths` (for baseline cohorts only);
- compare broad age patterns against official city totals, without treating agreement as proof of migration;
- sensitivity runs: Spain versus Madrid survival, last-year mortality fallback, half-age timing, terminal-age treatment, and inclusion/exclusion of estimated zones;
- inspect years between endpoints, if available, for discontinuities indicating administrative corrections, schema breaks or exceptional deregistration/re-registration. A January-to-January residual can contain these effects.

Publish a machine-readable QA summary and a human audit page. Any failed invariant blocks release; warnings require signed-off notes in the manifest.

## 12. Interpretation and limitations

The website must use this three-part language consistently:

- **Observed:** people registered in the padrón on the reference date.
- **Expected:** modelled survivors from the start population if they remained in the same area and followed the selected mortality schedule.
- **Observed-minus-expected residual:** a stock-accounting difference, not an observed flow or set of identified moves.

For ESP or EXT separately, the residual combines net entries/exits, acquisition or loss/reclassification of nationality, mortality mismatch, boundary/allocation error and padrón administrative effects. For ESP+EXT, nationality switching within the two exhaustive groups largely cancels, so interpretation as a **net residential-change proxy among cohorts alive at baseline** is stronger—but it still combines moves, registration effects and model error, and multiple moves cancel in a stock comparison.

Other limitations:

- registration differs from actual residence and can lag, especially for removals/renewals;
- period life tables describe a regional synthetic cohort, not section-specific risks or the actual baseline cohort;
- selective migration and mortality are not separable with these stocks;
- small-cell residuals are noisy even without sampling error;
- the binary nationality grouping hides heterogeneous origins and legal transitions;
- boundary interpolation, where unavoidable, adds modelled spatial uncertainty;
- ages 0–9 are outside the V1 cohort counterfactual, so headline totals do not describe the entire 2025 population;
- a 10-year window is intuitive and reveals cohort structure but accumulates boundary and classification changes.

## 13. Historical scope and configuration

Use 2015–2025 as the headline **only if** January files, annual mortality through 2024 and GIS vintages pass audit. It is preferable to 2014–2024 for communication and recency, while starting one year after the apparent archive begins provides a 2014 file for schema/reference-date diagnostics. Also build 2014–2024 as a validation comparison when sources permit.

The model configuration must contain dates rather than “2015” column names. It derives `k`, eligible endpoint ages, mortality years and labels. Later 2016–2026 should require only new source-manifest entries and a new zone version. Shorter windows are supported, but results across windows should not be ranked together without annualisation and clear labels.

## 14. Implementation phases and decision gates

### Phase 0 — source and feasibility audit (no public product)

1. Resolve all catalogue resources; archive metadata and exact files.
2. Profile every January file from 2014–2025 to identify schema/reference-date changes and administrative jumps.
3. Acquire 2015/2025 sections plus historical barrios/distritos; run the full change classification.
4. Confirm annual mortality dimensions/coverage and terminal ages.
5. Produce a feasibility report with population shares in exact/estimated/unreliable geography.

**Gate:** proceed to section MVP only if all endpoint totals reconcile and a high, predeclared population share (recommend ≥95%) is covered by unchanged/exact stable zones. Otherwise launch barrio/distrito first.

### Phase 1 — analytical MVP

- immutable acquisition, normalisation and schema contracts;
- exact harmonised zones and quality flags; exclude estimated/unreliable zones by default;
- sex-specific annual survival model for baseline cohorts ending at ages 10+;
- precomputed actual, expected, ESP, EXT and combined residuals at all reliable levels;
- age bands, rates, QA report and downloadable analytical data;
- no birth counterfactual and no naturalisation adjustment.

### Phase 2 — website MVP

- intro, default combined-rate map, area profile, city explorer and methodology;
- lazy static payloads, accessible charts and reliability disclosure;
- reproducible build/version manifest and performance budgets measured in CI.

### Phase 3 — robustness and coverage

- sensitivity displays; intermediate-year discontinuity diagnostics;
- carefully reviewed dasymetric estimates for otherwise important zones;
- comparison-window selector (begin with 2014–2024 as validation);
- uncertainty/suppression conventions for sparse and estimated cells.

### Phase 4 — optional research enhancements

- total-population birth counterfactual after fertility validation;
- naturalisation scenario only if it demonstrably adds stable explanatory value;
- richer origin/country-of-birth views where disclosure and data permit;
- additional periods as new data arrive.

## 15. First implementation tickets (after plan approval)

1. Create `sources.lock.yml` and a downloader that stores metadata, SHA-256 and retrieval timestamps.
2. Generate a 2014–2025 padrón schema/profile report before writing transformations.
3. Define canonical IDs and data contracts with tiny licensed fixtures.
4. Build the 2015/2025 geometry overlay report and review all changed graph components.
5. Extract and validate mortality probabilities; produce a city-level survival notebook/report.
6. Agree launch geography from the feasibility gate.
7. Implement model and additive aggregates, then the QA suite.
8. Benchmark real web payloads before choosing exact partition sizes or a frontend framework.

This order intentionally prevents UI work from hardening assumptions that the source and boundary audits may overturn.
