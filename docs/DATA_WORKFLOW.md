# Data workflow and contracts

All project paths resolve relative to the project JSON file. Start with `config/project.example.json`; its paths and empty resource selections are placeholders, not an executable official build.

## Acquire and pin

`sources.lock.yml` contains candidate catalogue, metadata, and cartography endpoints. Download catalogue XML first with `acquire --id madrid-catalogue`. `discover` lists XML resource URLs; identify actual historical January resources from archived metadata rather than constructing filenames.

A source entry uses `id`, HTTPS `url`, `role`, `sha256`, `bytes`, `reference_date`, `release_date`, `license`, and `reviewed_by`. First acquisitions are unverified content-addressed files at `raw_root/id/sha256`, with retrieval/header receipts. Pin the actual checksum and byte length after inspecting contents, date semantics, and licence. Changed pinned content fails acquisition and cannot silently replace an immutable file. Metadata discovery URLs must not stand in for the required endpoint releases or filtered mortality observations.

Add January 2014–2025 sources and both geometry vintages, historical barrio/district sources, independently published controls, Madrid/Spain annual life tables, and methodology metadata. Store date/revision semantics in evidence, including start-of-month versus end-of-month. No source checksum or validation outcome is supplied for unavailable official data.

## Profile and normalize

`config/schema-aliases.json` is a versioned alias registry. Its candidate schema is deliberately `reviewed: false`. Inspect raw bytes and set the explicit encoding/delimiter, header aliases, valid dates, ignored columns, optional independent `total_column`, and terminal-age convention before marking a version reviewed. Unexpected headers, invalid/suppressed counts, duplicate facts, impossible ages, ambiguous vintage parents and contradictory codes fail normalization.

The four source count columns become `male/female × ESP/EXT` facts. Canonical section IDs are padded Madrid province+municipality+district+section strings. `COD_DIST_SECCION` must be a documented local/full code; alternate numbering requires a reviewed schema adapter. Normalization writes CSV, dictionary-encoded Parquet, a profile containing checksum/raw header hex/ages/counts/parents, and an audit of excluded total/unknown rows. Open `100+` rows retain population as an explicitly open terminal cell; they never receive an exact-age cohort residual. Reconcile unknown ages independently rather than treating unknown population as an eligible cohort.

The config-driven `prepare` command uses `source_ingestion`:

```json
{
  "padron": [{"source_id":"padron-2015", "schema":"reviewed-v1", "reference_date":"2015-01-01", "output":"../data/intermediate/padron_2015.csv"}],
  "mortality": [{"source_id":"ine-selected-series", "selection":"ine-selection.json", "output":"../data/intermediate/mortality_madrid.csv"}],
  "gis": [{"source_id":"sections-2015", "format":"zip", "layer":"REVIEWED_LAYER", "id_field":"CUSEC", "prefix":"28079", "output":"../data/intermediate/sections_2015.geojson"}]
}
```

`annual_profiles` lists the resulting January profile JSON paths. `diagnose` or the build reports schema/section-count changes and population jumps. Such flags are administrative-discontinuity diagnostics, not estimates of migration.

## Mortality

Canonical mortality CSV: `year,age,sex,qx`. `sex` is `male` or `female`; qx must be finite in [0,1]. Every required annual cohort transition is present or modeling fails.

`mortality --measure qx|px|lx --units probability|per_1000|survivors` converts explicitly selected long-form rows. `lx` uses consecutive-age ratios; the final open age cannot be converted without a defensible method. `mx` is rejected. Do not mix territorial or time dimensions.

`ine --selection` selects the JSON table by exact metadata variable/value codes. Inspect and archive INE metadata before filling:

```json
{
  "dimensions":{"OFFICIAL_REGION_VARIABLE_CODE":"MADRID_VALUE_CODE", "OFFICIAL_FUNCTION_VARIABLE_CODE":"QX_VALUE_CODE"},
  "age_variable":"OFFICIAL_AGE_VARIABLE_CODE", "sex_variable":"OFFICIAL_SEX_VARIABLE_CODE",
  "age_codes":{"OFFICIAL_25_CODE":25}, "sex_codes":{"OFFICIAL_MALE_CODE":"male", "OFFICIAL_FEMALE_CODE":"female"},
  "measure":"qx", "units":"probability", "start_year":2015, "end_year":2025
}
```

Mappings must cover every selected age and sex. The documented adapter expects INE `MetaData` entries with `Variable.Codigo` and `Codigo`, and observations containing `Anyo` and `Valor`; changed API schemas require a reviewed adapter.

Provide `survival_reference`, independently derived from official `l_x` or another valid reference, for chain verification. Alternative full mortality CSVs go under `mortality_variants`, for example `Spain` or `declared-last-year-fallback`. Any last-year fallback must be explicitly documented and run as a variant; missing primary probabilities are never silently copied.

## Geography

`import-gis` uses GDAL to select Madrid by the audited ID field and transform archive geometry to EPSG:25830. Original archives remain immutable. Read/repair decisions require archived originals and documentation; automatic undisclosed polygon repair is not performed.

`overlay` writes all pairwise material overlaps, graph components, split/merge/redraw/missing/extra classifications, binary common-zone crosswalks, and projected zone GeoJSON. Exact components require equal dissolved unions within configured tolerance. Equal IDs alone do not establish equal boundaries. The report lists stable `zone_id` values; build a geography CSV containing those zone IDs and the audited hierarchy:

```csv
area_id,name,level,parent_id,boundary_status,boundary_method
2807901001,Section 001,section,B011,unchanged,unchanged
B011,Barrio,barrio,D01,unchanged,aggregate
D01,District,district,MAD,unchanged,aggregate
MAD,Madrid,city,,unchanged,aggregate
```

Exact changed zones use `exact_harmonisation,exact_aggregate`; severe failures use `unreliable,excluded`. A geometry review JSON maps each changed zone ID to a reviewer and explanatory note. The build verifies source geometry/population ID sets, same-vintage overlaps, municipality gaps/outside areas, historical parent equality/nesting and agreement between supplied quality and computed quality. Changed parents require new harmonized parent geometry, not assignment using current codes. The crosswalk and common-zone WKB are also written as Parquet.

`capacity_weights` is a research API for reviewed residential-capacity allocation, with vintage/licence checks and area-weight sensitivity. Fractional crosswalks require temporal residential evidence and explicit review. It does not automatically promote an unsuitable component into official section results; useful estimated zones still require a reviewed crosswalk and source-specific adapter. Parent allocations across changed administrative borders likewise require reviewed harmonized parent definitions.

## QA and official release

Published controls are independently sourced JSON records:

```json
[{"year":2015,"area_id":"MAD","population":123456,"tolerance":0}]
```

The illustrative count above is a placeholder. Full-population controls are required for every barrio, district and city at both endpoints; optional age/nationality controls are supported. Controls reconcile births and terminal observations as well as cohort-eligible ages.

`evidence.json` contains `source_checksums`, `reference_dates`, `annual_profiles`, `published_totals`, `mortality_coverage`, `boundary_audit`, `historical_parents`, `independent_survival`, `sensitivity_review`, and `licensing`. Each entry requires `passed: true`, `reviewed_by`, a project-relative `artifact` path, and its `sha256`. Checksummed artifacts must exist and match; empty claims cannot release data. The `warnings` array requires signed reviewer notes. These are records of completed reviews, not fields to fill before the evidence exists.

Arithmetic QA independently checks sex/nationality sums, survivors ≤ baseline, hierarchy additivity and the stock identity `residual = actual − baseline + modeled deaths`. A failed invariant blocks every build. Official mode additionally enforces source locks, profiles, parent/boundary checks, complete controls and reviewed evidence. Demonstrations are allowed without empirical gates and are visibly labeled.

The 95% exact-coverage gate controls the recommended launch level. Default web bundles use exact-only inputs; parent/city counts explicitly disclose subset coverage when estimated/unreliable leaves are excluded. Inclusive research bundles retain quality flags and suppress unreliable residuals in the UI.

## Export and research

Outputs include sex-level cohort detail, area index/centroid/quality, age bands, map indicators/denominators/ranks, and composition Parquet; CSV carries the same boundary flags. Sex-specific survival is computed before summing. Age bands sum counts before calculating rates. Small expected denominators suppress rates while retaining additive counts. Terminal ages and cohorts born during the interval have observed-only counts.

Build output contains hashed JSON and gzip payloads, quantized TopoJSON per level, lazy area profiles, methodology/source/QA records, `audit.html`, and machine reports. Unsimplified projected analysis geometry remains offline. The manifest binds configuration, hashes, code commit and source-content hash, geography version, and compressed budgets. Serve hashed assets with immutable caching, and manifests/catalog with revalidation.

The catalog contains one independent entry per window, with `manifest` pointing at its exact tier and `inclusive_manifest` at its research tier. Additional periods need their own source/config/zone audit and build; do not compare unannualized ranks across periods.

Optional `research.fertility` CSV uses `year,age,asfr_per_1000`; `research.nationality_hazards` uses `year,age,sex,hazard`. They produce research reports, never overwrite primary residuals, and have no inferred nationality-at-birth assignment. Birth validation must compare projected births with observed city births. Nationality variants must demonstrate useful and stable explanatory improvement before public presentation. Richer origin views remain dependent on source-specific definitions and disclosure validation.
