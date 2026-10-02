# Independent historical parent sources

Independent municipal parent geometry and official section-change records are now acquired and pinned. The registry corroborates 33 of the 34 unchanged-geometry parent exceptions. **No endpoint parent geometry is approved:** candidate layers have temporal uncertainty and substantial containment discrepancies against the INE section cartography.

## Acquired sources

The official CKAN catalogue exposes [municipal barrios](https://datos.madrid.es/dataset/300496-0-barrios-madrid), [administrative limits](https://datos.madrid.es/dataset/900012-0-limites-administrativos-mapas), [dated birth maps](https://datos.madrid.es/dataset/300611-0-nacimientos-mapas), and [section-history documentation](https://datos.madrid.es/dataset/300724-0-seccionado-censal-mapas). Exact download URLs, hashes and sizes are pinned in the source lock. The manifest now contains **40 verified snapshots**.

The downloaded historical-division ZIP contains eleven nested archives, from 1612 through **1987**. Its newest division has 128 barrio polygons and 21 district polygons in EPSG:25830. The 1987 label does not certify January 2015 validity.

The live barrio/district downloads contain 131 and 21 polygons. The pinned Geoportal metadata explicitly documents a municipal boundary alteration dated **22 October 2025** and a further adjustment in **2026**. Those live layers cannot be substituted for January 2025.

The `20250101_nacimientos.zip` statistical map archive contains 131 barrio and 21 district polygons. Its shapefile members are dated **2 October 2025**, before the October municipal alteration. That strengthens its candidacy compared with the live service, but a statistical filename and ZIP timestamp are not an explicit January boundary-validity interval. Birth counts in this archive are not used in the demographic model.

## Independent containment checks

All six candidate layers were read with explicit field/encoding contracts, normalized parent codes and EPSG:25830 validation. The reader rejects invalid/empty/duplicate polygons, unexpected feature counts and encoding/CRS drift. No geometry repairs were performed.

Each INE section was compared with the union of its raw-declared parents. Multiple raw memberships remain explicit; the largest group is not selected. The containment threshold allows at most 0.1% of a section's land area outside its declared parent.

| Candidate layer | Endpoint tested | Sections outside declared parent at strict tolerance |
|---|---|---:|
| Historical 1987 barrios | 2015 | 926 / 2,420 |
| Historical 1987 districts | 2015 | 354 / 2,420 |
| January-2025-labelled statistical barrios | 2025 | 932 / 2,462 |
| January-2025-labelled statistical districts | 2025 | 340 / 2,462 |
| Live 2026 barrios | 2025 | 939 / 2,462 |
| Live 2026 districts | 2025 | 349 / 2,462 |

Many failures may concern different precision or adjustments to road axes, but not all are tiny. In the January-2025-labelled layers, **50 barrio cases and 20 district cases exceed 5% outside area**. Section `2807910217` has approximately 42.4% outside its declared barrio and district. The older historical layer puts approximately 98.7% of the 2015 polygon outside its declared parent. These are measured map incompatibilities; they do not show that the people or raw parent codes are wrong. Increasing tolerance or assigning the nearest/majority parent would conceal the problem.

Full source contracts, labels, layer timestamps, population accounting and exception metrics are in [parent-candidates.json](audit/parent-candidates.json) and [config/parent-candidates.json](../config/parent-candidates.json). Temporal validity remains false for all six candidates. The parent-vintage guard rejects missing, malformed or out-of-range date evidence.

## Official section-change registry

The municipality's historical workbook contains **2,713 records**, titled “Historia del seccionado 1988 - 2024”, with creation, deletion and modification fields, previous barrio codes, origin/destination sections and notes.

Using creation-inclusive/deletion-exclusive intervals for this audit:

- All **2,420 ordinary 2015 section memberships** match. The four exceptional no-polygon codes remain outside the registry.
- **2,460 raw 2025 section memberships** match. Section `2807908130` is absent from the registry; `2807919036` has raw memberships in both `1901` and `1902`, while the registry records `1902`; and `2807919052` lacks a creation date in registry row 2546.
- The workbook documents **54 parent reassignments** and corroborates **33 of the 34** unchanged-polygon parent exceptions in the boundary review. The remaining unchanged-polygon case is the split membership of `2807919036`.

**23 modification-date fields contain `20171606`**, invalid as YYYYMMDD. They are preserved verbatim. Where a previous barrio is recorded, only the year is used to bracket endpoints strictly before or after 2017; no June/October date is invented. Within-year comparisons would remain unresolved. Carrying a workbook titled through 2024 into January 2025 is provisional, even where the raw memberships agree.

These records help explain historical membership changes, but do not reconstruct exact polygon boundaries or locate individual people within split sections. Evidence, preserved date errors and all discrepancies are in [section-history.json](audit/section-history.json).

## Reproduce and continue

```bash
pip install '.[audit-gis,audit-history]'
python -m madrid_demography.cli acquire --lock sources.lock.yml --root data/raw
python scripts/audit_parent_candidates.py
python scripts/audit_section_history.py
```

65 tests pass, including temporal validity, malformed dates, partial containment, missing and ambiguous parents, and registry dates that must not be silently repaired. Ruff lint and formatting pass. All 40 pinned source hashes and byte sizes were verified.

Next, build a **city-level research calculation** using the conditional count policy and national mortality, including exceptional population. This can test the survival model while the spatial publication gate remains closed. Barrio publication still needs January-valid parent cartography or coordinate-based official change records, reconciliation with the section geometry, and the remaining analytical release reviews.
