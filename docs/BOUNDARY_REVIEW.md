# Boundary and historical parent review

The 2015–2025 section overlay supports stable geographic aggregates, but it does **not** establish comparable barrio totals. Raw historical membership reveals 50 parent exceptions. Official small-area publication remains blocked on independent historical parent boundaries and analytical review.

## Geometry findings

The review uses both pinned INE archives in EPSG:25830 and the actual publication pipeline's overlay. District and section attributes (`CDIS`, `CUDIS`, `CSEC`, `CUSEC`) agree throughout both archives. Polygons are valid, and both vintages pass the pipeline's within-vintage overlap audit.

| Component class | Components |
|---|---:|
| Unchanged section geometry | 2,221 |
| Splits | 60 |
| Merges | 47 |
| Many-to-many redraws | 15 |
| Total | 2,343 |

All 122 changed component unions agree within tolerance. The maximum symmetric-difference ratio is **1.43 × 10⁻⁷**, well below the 0.001 criterion. The component sets are identical to the earlier provisional audit even with the pipeline's smaller material-overlap threshold (10⁻⁶ of the smaller polygon's area). The code calls many-to-many components `materially_redrawn`; in these 15 cases that describes internal section rearrangement, while the common outer union remains compatible with exact aggregation.

Population accounting conserves all known city counts: 12 people in exceptional 2015 section codes lack polygons; in 2025 three people lack a polygon and two lack section codes. These exceptions remain separate from mapped section results.

## Parent findings

Parent assignments are read from each endpoint's full raw barrio/section grain, including zero and blank count rows. A majority-count barrio is never selected to resolve ambiguity. Matching raw codes provide corroboration only; they do not replace an independently dated barrio boundary layer.

| Parent status | Components |
|---|---:|
| One matching raw parent code at both endpoints | 2,293 |
| One raw barrio reassigned between endpoints | 41 |
| Component spans multiple barrios | 8 |
| Section has multiple raw barrio memberships | 1 |

Of the 50 exceptions, **34 have unchanged section geometry**. Examples include section `2807918047`, whose raw barrio changes from `1801` to `1803`, and sections in district 19 changing among `1901`, `1902` and `1903`. The polygons alone cannot resolve these changes.

Section `2807919036` has one person assigned to barrio `1901` and 2,058 assigned to `1902` in 2025. Both raw memberships remain represented.

One common component, `Z-57b172e30c85`, spans districts 16 and 21 and five barrio codes. It combines eight old and nineteen new sections, with 14,912 known people in 2015 and 40,929 in 2025. Assigning this entire stable zone to a single current district or barrio would change the hierarchy.

| Endpoint | Known population in zones with one matching raw barrio code | Share of known city population |
|---|---:|---:|
| 2015 | 3,029,099 | 96.17% |
| 2025 | 3,344,556 | 94.47% |

The earlier >99.99% candidate coverage concerned section geometry alone. The 94.47% figure is a narrower raw-parent feasibility screen, not an approved coverage measure and not a replacement definition of the plan's geometry gate. It shows why geometry coverage cannot justify publishing comparable barrio totals.

## Review artifacts and reproduction

The [seven-page atlas](../reports/boundary-review-atlas.pdf) shows all 122 changed components plus the 34 unchanged components with parent exceptions. Blue outlines are 2015 and orange outlines are 2025. Codex inspected all seven contact-sheet pages; the outer-union coincidence and internal split/merge patterns are consistent with the numerical results. This visual inspection is not an independent verification of historical parent boundaries or an analytical release approval.

The full inventory is in [audit/boundary-review.csv](audit/boundary-review.csv) and [audit/boundary-review.json](audit/boundary-review.json), including source hashes, land area, known population, parent codes, geometry metrics and accounting exceptions. Atlas hashes and plotted component IDs are in [audit/boundary-atlas.json](audit/boundary-atlas.json). Audit tables deliberately use separate column names from the publication crosswalk.

```bash
pip install '.[audit-gis,audit-plots]'
python scripts/review_official_boundaries.py
python scripts/render_boundary_atlas.py
```

58 tests pass. Parent tests cover reassignment despite identical section IDs, cross-district zones, ambiguous membership, unknown codes, missing evidence and conservation of exceptional population rows. Ruff lint and formatting pass.

## Next step

Acquire independently dated Madrid barrio and distrito boundaries, or official change records sufficient to construct and validate common historical parents. Start with districts 18 and 19 and the cross-district component above. Overlay those parents against both section vintages and retain explicit exceptions. Current boundaries or raw-code dissolves cannot serve as independent 2015 boundary evidence.

City-level research calculations can proceed without assigning a barrio to these components, provided they include exceptional population and retain the conditional count and mortality caveats. They would still need independently reproduced survival and the remaining release reviews before official publication.
