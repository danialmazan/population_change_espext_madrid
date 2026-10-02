# Observed research results and validation

Updated 2 October 2026. These are research results from observed municipal data, not an official statistical release. The official release gates remain closed.

## City results

Baseline ages 0–89 are followed to ages 10–99. National INE table 27153 annual sex-specific risks are compounded along each ageing cohort. The same sex-specific schedule is applied to ESP and EXT. Ages born during the interval and endpoint ages 100+ are shown separately.

| Window | Eligible baseline | Expected survivors | Observed endpoint | Residual | Per 1,000 expected |
|---|---:|---:|---:|---:|---:|
| 2015-2025 | 3,109,701 | 2,827,032.405 | 3,275,658 | 448,625.595 | 158.691 |
| 2014-2024 | 3,138,522 | 2,854,624.882 | 3,207,983 | 353,358.118 | 123.784 |

The 2015–2025 result excludes 262,476 endpoint children aged 0–9 and 2,230 people aged 100+. One baseline record with age 135 is excluded from analytical composition and remains in source accounting. A residual is a stock difference; it cannot separate migration, registration changes, nationality reclassification or model error.

## Independent survival check

A separate implementation propagates each population count annually with 40-digit Decimal arithmetic using published survivor ratios l[x+1,y] / l[x,y]. It does not call the production qx survival helper. Every eligible age/sex/nationality cell passes a bound derived from the six-decimal precision of the published qx-per-thousand and lx values.

| Window | Cells checked | Maximum cell difference | Total expected difference | Total rounding bound |
|---|---:|---:|---:|---:|
| 2015-2025 | 360 | 0.00005068 | 0.00001781 | 0.01591917 |
| 2014-2024 | 360 | 0.00004784 | 0.00015961 | 0.01606745 |

## Mortality and terminal-age sensitivity

Terminal cutoffs change the cohorts being compared. Compare Madrid and national mortality at the same endpoint cutoff of 95. The Madrid variant scales the national single-age hazard pattern so the product of annual survival within each closed age band reproduces the published Madrid band survival. This is an approximation, not an observed single-age Madrid schedule. Open ages are never expanded.

| Window | Variant | Endpoint ages | Expected | Observed | Residual |
|---|---|---|---:|---:|---:|
| 2015–2025 | Spain under90 | 10–89 | 2,767,820.4 | 3,215,476 | 447,655.6 |
| 2015–2025 | Spain under95 | 10–94 | 2,813,585.8 | 3,262,065 | 448,479.2 |
| 2015–2025 | Spain under100 | 10–99 | 2,827,032.4 | 3,275,658 | 448,625.6 |
| 2015–2025 | Spain half-age under100 | 10–99 | 2,814,985.3 | 3,275,658 | 460,672.7 |
| 2015–2025 | Spain lx under100 | 10–99 | 2,827,032.4 | 3,275,658 | 448,625.6 |
| 2015–2025 | Madrid approximation under95 | 10–94 | 2,838,073.9 | 3,262,065 | 423,991.1 |
| 2014–2024 | Spain under90 | 10–89 | 2,797,219.4 | 3,150,151 | 352,931.6 |
| 2014–2024 | Spain under95 | 10–94 | 2,841,968.0 | 3,195,405 | 353,437.0 |
| 2014–2024 | Spain under100 | 10–99 | 2,854,624.9 | 3,207,983 | 353,358.1 |
| 2014–2024 | Spain half-age under100 | 10–99 | 2,842,542.2 | 3,207,983 | 365,440.8 |
| 2014–2024 | Spain lx under100 | 10–99 | 2,854,624.9 | 3,207,983 | 353,358.1 |
| 2014–2024 | Madrid approximation under95 | 10–94 | 2,865,779.9 | 3,195,405 | 329,625.1 |

At endpoint ages 10–94, the 2015–2025 national residual is 448,479.2 and the Madrid approximation is 423,991.1 (24,488.1 fewer). Half-age interpolation at ages 10–99 raises the national residual by 12,047.1. These are scenario differences, not confidence intervals. The denominator threshold remains 20 expected survivors; rates below it are suppressed.

## Annual reconciliation and intermediate years

Eleven of the twelve January section files exactly match all 400 city age/sex/nationality cells and all four full-population monthly controls. Raw blanks remain unchanged. For matched years only, research aggregation conditionally treats blanks as zero under the assumptions of the same complete universe, nonnegative counts, correct known cells and no compensating errors.

| Year | Raw known total | Raw blank cells | Controls match | Invalid-age people |
|---|---:|---:|---|---:|
| 2014 | 3,176,508 | 296,007 | Yes | 0 |
| 2015 | 3,149,663 | 304,657 | Yes | 1 |
| 2016 | 3,174,945 | 302,903 | Yes | 0 |
| 2017 | 3,191,117 | 300,262 | Yes | 0 |
| 2018 | 3,231,062 | 297,248 | Yes | 0 |
| 2019 | 3,275,195 | 289,584 | Yes | 0 |
| 2020 | 3,345,894 | 280,036 | Yes | 0 |
| 2021 | 3,292,949 | 0 | No | 1 |
| 2022 | 3,296,033 | 279,395 | Yes | 1 |
| 2023 | 3,352,448 | 0 | Yes | 0 |
| 2024 | 3,473,648 | 0 | Yes | 0 |
| 2025 | 3,540,364 | 0 | Yes | 0 |

**2021 fails reconciliation.** The section file totals 3,292,949; the monthly bank totals 3,327,119, a gap of 34,170. There are 394 age-control discrepancies. No local zero inference is approved for that year. The intermediate-year city calculation uses the bank’s explicit city age/sex/nationality counts, with an explicit source-change flag. This discrepancy remains an empirical release blocker.

The intermediate comparison follows a fixed baseline population aged 0–89 in 2015. Endpoint ages increase each year; no cohorts are silently added to the baseline.

| Endpoint | Eligible observed | Expected | Residual |
|---|---:|---:|---:|
| 2016 | 3,116,241 | 3,085,989.6 | 30,251.4 |
| 2017 | 3,109,084 | 3,062,020.8 | 47,063.2 |
| 2018 | 3,126,292 | 3,036,343.6 | 89,948.4 |
| 2019 | 3,148,020 | 3,009,532.5 | 138,487.5 |
| 2020 | 3,194,837 | 2,982,500.9 | 212,336.1 |
| 2021 | 3,157,725 | 2,949,673.0 | 208,052.0 |
| 2022 | 3,110,181 | 2,919,166.0 | 191,015.0 |
| 2023 | 3,144,355 | 2,887,436.0 | 256,919.0 |
| 2024 | 3,236,410 | 2,857,330.4 | 379,079.6 |
| 2025 | 3,275,658 | 2,827,032.4 | 448,625.6 |

## Spatial comparability and small-area results

The research overlay contains 2,343 common section zones: 2,221 unchanged and 122 changed components. Every whole section maps once with weight 1. The maximum outer-union symmetric difference ratio is 0.000000143, below the predeclared 0.001 tolerance. No population is allocated by land area.

All parent codes attached to each common zone are linked across the two vintages. Connected parent groups are pooled in full, yielding 123 common barrio areas and 20 common district areas. This retains ambiguous memberships instead of choosing a majority. These are derived research aggregates, not approved historical administrative boundaries.

The pooled district is Hortaleza + Barajas. Pooled barrio groups are Valdefuentes + Aeropuerto + Casco Histórico de Barajas + Timón + Corralejos; Casco Histórico de Vallecas + Ensanche de Vallecas; and all four Vicálvaro barrios. Stable parent-code groups are still labelled as common research areas because independent dated parent boundaries have not been verified.

Spatial results omit 12 people with unmapped section codes in 2015 and 5 in 2025; one additional baseline person has invalid age 135. The mapped eligible baseline is 3,109,689, expected 2,827,020.973, actual 3,275,653 and residual 448,632.027. The whole-city result includes the exceptional geography and is available separately.

All section, common barrio, common district and mapped-city results pass sex/nationality sums, survivor bounds, stock accounting and additive hierarchy checks. Download the area inventory in [research-area-results.csv](../reports/research-area-results.csv). Full cohort detail, composition and age-band outputs are packaged in the explorer.

## Source attribution and licensing

Population: Ayuntamiento de Madrid, municipal padrón January snapshots 2014–2025 and Banco de Datos Municipal January city controls, retrieved 2 October 2026. Mortality and census-section geometry: Instituto Nacional de Estadística (INE), national table 27153, Madrid closed bands in table 27154, census sections 2015/2025.

The municipal padrón catalogues explicitly declare CC BY 4.0. The archived INE reuse terms declare CC BY 4.0 as the general statistical-information licence absent a specific exception. The source lock records evidence for the inputs used in research; unresolved licence metadata for other audit candidates is not silently filled. Transformations include conditional zero aggregation, cohort survival, common-zone unions and display simplification. These transformations are not endorsed by Madrid or INE.

## Explorer and release checks

The observed research explorer has three datasets: 2015–2025 common areas, 2015–2025 whole city and 2014–2024 whole city. Preset indicators are partitioned by spatial level and age selection; profiles are lazy-loaded. The full checksum inventory is a separate downloadable audit artifact.

| Dataset | Index + indicators gzip | Typical initial data gzip | Passed |
|---|---:|---:|---|
| 2014-2024-city | 732 bytes | 20,600 bytes | Yes |
| 2015-2025-areas | 291,220 bytes | 322,867 bytes | Yes |
| 2015-2025-city | 731 bytes | 20,791 bytes | Yes |

Typical initial data includes the manifest, index, indicators, default map geometry and first area profile. Every artifact and CSV/Parquet download has a verified checksum. Limits remain 500 KB initial data, 1 MB per geometry layer and 100 KB per profile.

Local validation: 70 Python tests pass. Both fixture and observed research browser checks pass, including maps, spatial levels, three research windows, lazy indicators, cohort exclusions, custom ages, keyboard selection and mobile overflow. No research-browser JavaScript errors or failed HTTP responses were observed.

Official statistical release remains blocked by the 2021 discrepancy, historical administrative boundary validity, changed-component analytical approval, and final empirical review/signoffs. Research publication does not open those gates.

## Reproduction

Use Python 3.12 and requirements.lock, plus PyShp 2.3.1 for the source geometry reader. Acquire the hash-pinned sources, then run the commands below. The checked-in control responses are hash-bound to their exact request parameters; fetching them again is optional and may reveal source revisions.

```sh
python -m madrid_demography.cli acquire --lock sources.lock.yml --root data/raw
python scripts/build_research.py
python scripts/check_research_budgets.py
python scripts/check_research_browser.py
```

The website is built in data/derived/research-site. GitHub publication uses the gh-pages branch; repository Pages configuration is a separate hosting setting. The implementation branch retains code, audit evidence, results, PDF and the downloadable website archive.
