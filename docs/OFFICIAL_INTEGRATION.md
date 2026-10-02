# Official input integration — 2 October 2026

The current pipeline now shares a pinned manifest with the empirical audit: 29 immutable snapshots covering January 2014–2025, 2015/2025 section geometries, independent annual controls, municipal methodology and mortality sources. Raw files remain outside Git. `python -m madrid_demography.cli acquire --lock sources.lock.yml --root data/raw` restores the newer pipeline's extensionless, checksum-addressed layout. Audit readers resolve files under the supplied raw root; receipt paths from another machine are not used for pinned inputs.

The provisional boundary audit additionally needs `pip install ".[audit-gis]"` (PyShp); the publication GIS importer continues to use GDAL.

## New corroboration

The historical catalogue's January 2015 TXT and CSV exports contain the same 232,993 rows, including identical blank cells. This rules out a CSV-specific loss; it does not define blank semantics.

The municipal statistical bank's public monthly query returns exactly the same four sex/nationality totals as the CSV profiles in both endpoint years:

| January | Known CSV population | Monthly bank total | Difference |
|---|---:|---:|---:|
| 2015 | 3,149,663 | 3,149,663 | 0 |
| 2025 | 3,540,364 | 3,540,364 | 0 |

The responses are retained in `docs/audit/monthly-bank-2015.json` and `monthly-bank-2025.json`; their hashes and comparisons are in `integration.json`. Source: `https://servpub.madrid.es/CSEBD_WBINTER/seleccionSerie.html?numSerie=0301000000001`. Its public UI posts JSON to `detalleSerie.html` with `accionFormulario=consultarDatosBarrio`, January, the endpoint year, all districts/barrios/ages, total nationality and total sex, and absolute values. These saved controls corroborate the monthly extraction. They are not revised annual or INE legal population controls.

Known totals matching exhaustive monthly controls is evidence against omitted positive population at city level. It is not an explicit source definition of each of the 304,657 baseline blanks. Audit exports continue to retain nulls; the model-facing normaliser continues to reject blanks.

## Pipeline changes

The strict model normaliser can now use a versioned `barrio_code_format: district_times_100` (101 becomes 0101; 1002 remains 1002), and explicitly listed `open_age_labels`, including `100 o +`. Existing fixture conventions remain available. Parent conflicts, missing counts, duplicate cells and invalid ages still stop model preparation. The audit normaliser preserves exceptional and split-parent geography for review.

Audit configuration remains separate from `project.example.json`. An executable official model configuration cannot be completed until nullable counts, geography and historical parent contracts have been resolved. No official explorer bundle is published by these changes.

## Validation and next step

49 automated tests pass. `scripts/check_official_inputs.py` verifies all 29 source hashes and sizes, full CSV/TXT equality, and all four monthly control totals. Endpoint audit exports conserve known counts and null counts; national mortality covers all 2,000 required sex/year/age cells.

Next: approve a documented monthly-source and blank-cell policy, then review changed geometry components and historical barrio/district parents. Annual revised differences remain 7,672 people in 2015 and 12,440 in 2025; the monthly controls show these differences are between published series, rather than a failure to sum the CSV. The exact revisions remain unexplained. Independent survival reproduction, regional mortality sensitivity, and licensing review also remain required before an official release.
