"""Render the checked research evidence as a concise, source-bound report."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
r = json.loads((ROOT / "docs/audit/research-results.json").read_text())
performance = json.loads((ROOT / "docs/audit/research-performance.json").read_text())
lines = [
    "# Observed research results and validation",
    "",
    "Updated 2 October 2026. These are research results from observed municipal data, not an official statistical release. The official release gates remain closed.",
    "",
    "## City results",
    "",
    "Baseline ages 0–89 are followed to ages 10–99. National INE table 27153 annual sex-specific risks are compounded along each ageing cohort. The same sex-specific schedule is applied to ESP and EXT. Ages born during the interval and endpoint ages 100+ are shown separately.",
    "",
    "| Window | Eligible baseline | Expected survivors | Observed endpoint | Residual | Per 1,000 expected |",
    "|---|---:|---:|---:|---:|---:|",
]
for window, s in r["city_windows"].items():
    lines.append(
        f"| {window} | {s['baseline']:,.0f} | {s['expected']:,.3f} | {s['actual']:,.0f} | {s['residual']:,.3f} | {s['residual_per_1000']:.3f} |"
    )
lines += [
    "",
    "The 2015–2025 result excludes 262,476 endpoint children aged 0–9 and 2,230 people aged 100+. One baseline record with age 135 is excluded from analytical composition and remains in source accounting. A residual is a stock difference; it cannot separate migration, registration changes, nationality reclassification or model error.",
    "",
    "## Independent survival check",
    "",
    "A separate implementation propagates each population count annually with 40-digit Decimal arithmetic using published survivor ratios l[x+1,y] / l[x,y]. It does not call the production qx survival helper. Every eligible age/sex/nationality cell passes a bound derived from the six-decimal precision of the published qx-per-thousand and lx values.",
    "",
    "| Window | Cells checked | Maximum cell difference | Total expected difference | Total rounding bound |",
    "|---|---:|---:|---:|---:|",
]
for window, s in r["independent_survival"].items():
    lines.append(
        f"| {window} | {s['cells']} | {s['maximum_cell_difference']:.8f} | {abs(s['total_expected_qx'] - s['total_expected_lx']):.8f} | {s['total_rounding_bound']:.8f} |"
    )
lines += [
    "",
    "## Mortality and terminal-age sensitivity",
    "",
    "Terminal cutoffs change the cohorts being compared. Compare Madrid and national mortality at the same endpoint cutoff of 95. The Madrid variant scales the national single-age hazard pattern so the product of annual survival within each closed age band reproduces the published Madrid band survival. This is an approximation, not an observed single-age Madrid schedule. Open ages are never expanded.",
    "",
    "| Window | Variant | Endpoint ages | Expected | Observed | Residual |",
    "|---|---|---|---:|---:|---:|",
]
for s in r["sensitivities"]:
    label = (
        s["scenario"]
        .replace("national_endpoint_", "Spain ")
        .replace("national_half_age_", "Spain half-age ")
        .replace("national_lx_", "Spain lx ")
        .replace("Madrid_closed_band_approximation_", "Madrid approximation ")
    )
    lines.append(
        f"| {s['start_year']}–{s['end_year']} | {label} | 10–{s['terminal_age'] - 1} | {s['expected']:,.1f} | {s['actual']:,.0f} | {s['residual']:,.1f} |"
    )
lines += [
    "",
    "At endpoint ages 10–94, the 2015–2025 national residual is 448,479.2 and the Madrid approximation is 423,991.1 (24,488.1 fewer). Half-age interpolation at ages 10–99 raises the national residual by 12,047.1. These are scenario differences, not confidence intervals. The denominator threshold remains 20 expected survivors; rates below it are suppressed.",
    "",
    "## Annual reconciliation and intermediate years",
    "",
    "Eleven of the twelve January section files exactly match all 400 city age/sex/nationality cells and all four full-population monthly controls. Raw blanks remain unchanged. For matched years only, research aggregation conditionally treats blanks as zero under the assumptions of the same complete universe, nonnegative counts, correct known cells and no compensating errors.",
    "",
    "| Year | Raw known total | Raw blank cells | Controls match | Invalid-age people |",
    "|---|---:|---:|---|---:|",
]
for s in r["annual_controls"]:
    lines.append(
        f"| {s['year']} | {s['known_total']:,} | {s['raw_blank_cells']:,} | {'Yes' if s['monthly_controls_matched'] else 'No'} | {s['invalid_age_known_population']} |"
    )
lines += [
    "",
    "**2021 fails reconciliation.** The section file totals 3,292,949; the monthly bank totals 3,327,119, a gap of 34,170. There are 394 age-control discrepancies. No local zero inference is approved for that year. The intermediate-year city calculation uses the bank’s explicit city age/sex/nationality counts, with an explicit source-change flag. This discrepancy remains an empirical release blocker.",
    "",
    "The intermediate comparison follows a fixed baseline population aged 0–89 in 2015. Endpoint ages increase each year; no cohorts are silently added to the baseline.",
    "",
    "| Endpoint | Eligible observed | Expected | Residual |",
    "|---|---:|---:|---:|",
]
for s in r["intermediate_years"]:
    lines.append(
        f"| {s['endpoint_year']} | {s['actual']:,.0f} | {s['expected']:,.1f} | {s['residual']:,.1f} |"
    )
lines += [
    "",
    "## Spatial comparability and small-area results",
    "",
    "The research overlay contains 2,343 common section zones: 2,221 unchanged and 122 changed components. Every whole section maps once with weight 1. The maximum outer-union symmetric difference ratio is 0.000000143, below the predeclared 0.001 tolerance. No population is allocated by land area.",
    "",
    "All parent codes attached to each common zone are linked across the two vintages. Connected parent groups are pooled in full, yielding 123 common barrio areas and 20 common district areas. This retains ambiguous memberships instead of choosing a majority. These are derived research aggregates, not approved historical administrative boundaries.",
    "",
    "The pooled district is Hortaleza + Barajas. Pooled barrio groups are Valdefuentes + Aeropuerto + Casco Histórico de Barajas + Timón + Corralejos; Casco Histórico de Vallecas + Ensanche de Vallecas; and all four Vicálvaro barrios. Stable parent-code groups are still labelled as common research areas because independent dated parent boundaries have not been verified.",
    "",
    "Spatial results omit 12 people with unmapped section codes in 2015 and 5 in 2025; one additional baseline person has invalid age 135. The mapped eligible baseline is 3,109,689, expected 2,827,020.973, actual 3,275,653 and residual 448,632.027. The whole-city result includes the exceptional geography and is available separately.",
    "",
    "All section, common barrio, common district and mapped-city results pass sex/nationality sums, survivor bounds, stock accounting and additive hierarchy checks. Download the area inventory in [research-area-results.csv](../reports/research-area-results.csv). Full cohort detail, composition and age-band outputs are packaged in the explorer.",
    "",
    "## Source attribution and licensing",
    "",
    "Population: Ayuntamiento de Madrid, municipal padrón January snapshots 2014–2025 and Banco de Datos Municipal January city controls, retrieved 2 October 2026. Mortality and census-section geometry: Instituto Nacional de Estadística (INE), national table 27153, Madrid closed bands in table 27154, census sections 2015/2025.",
    "",
    "The municipal padrón catalogues explicitly declare CC BY 4.0. The archived INE reuse terms declare CC BY 4.0 as the general statistical-information licence absent a specific exception. The source lock records evidence for the inputs used in research; unresolved licence metadata for other audit candidates is not silently filled. Transformations include conditional zero aggregation, cohort survival, common-zone unions and display simplification. These transformations are not endorsed by Madrid or INE.",
    "",
    "## Explorer and release checks",
    "",
    "The observed research explorer has three datasets: 2015–2025 common areas, 2015–2025 whole city and 2014–2024 whole city. Preset indicators are partitioned by spatial level and age selection; profiles are lazy-loaded. The full checksum inventory is a separate downloadable audit artifact.",
    "",
    "| Dataset | Index + indicators gzip | Typical initial data gzip | Passed |",
    "|---|---:|---:|---|",
]
for s in performance:
    lines.append(
        f"| {s['window']} | {s['initial_index_indicator_gzip_bytes']:,} bytes | {s['typical_data_gzip_bytes']:,} bytes | Yes |"
    )
lines += [
    "",
    "Typical initial data includes the manifest, index, indicators, default map geometry and first area profile. Every artifact and CSV/Parquet download has a verified checksum. Limits remain 500 KB initial data, 1 MB per geometry layer and 100 KB per profile.",
    "",
    "Local validation: 70 Python tests pass. Both fixture and observed research browser checks pass, including maps, spatial levels, three research windows, lazy indicators, cohort exclusions, custom ages, keyboard selection and mobile overflow. No research-browser JavaScript errors or failed HTTP responses were observed.",
    "",
    "Official statistical release remains blocked by the 2021 discrepancy, historical administrative boundary validity, changed-component analytical approval, and final empirical review/signoffs. Research publication does not open those gates.",
    "",
    "## Reproduction",
    "",
    "Use Python 3.12 and requirements.lock, plus PyShp 2.3.1 for the source geometry reader. Acquire the hash-pinned sources, then run the commands below. The checked-in control responses are hash-bound to their exact request parameters; fetching them again is optional and may reveal source revisions.",
    "",
    "```sh",
    "python -m madrid_demography.cli acquire --lock sources.lock.yml --root data/raw",
    "python scripts/build_research.py",
    "python scripts/check_research_budgets.py",
    "python scripts/check_research_browser.py",
    "```",
    "",
    "The website is built in data/derived/research-site. GitHub publication uses the gh-pages branch; repository Pages configuration is a separate hosting setting. The implementation branch retains code, audit evidence, results, PDF and the downloadable website archive.",
]
(ROOT / "docs/RESEARCH_RESULTS.md").write_text("\n".join(lines) + "\n")
fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
years = [s["endpoint_year"] for s in r["intermediate_years"]]
axes[0].plot(
    years,
    [s["actual"] / 1e6 for s in r["intermediate_years"]],
    label="Observed",
    marker="o",
)
axes[0].plot(
    years,
    [s["expected"] / 1e6 for s in r["intermediate_years"]],
    label="Expected survivors",
    marker="o",
)
axes[0].set(
    xlabel="1 January endpoint",
    ylabel="Million people",
    title="Fixed baseline cohort ages 0–89 in 2015",
)
axes[0].axvline(2021, alpha=0.2, color="red")
axes[0].legend(frameon=False)
axes[0].grid(alpha=0.15)
variants = [
    s
    for s in r["sensitivities"]
    if s["start_year"] == 2015 and "national_lx" not in s["scenario"]
]
labels = [
    "Spain, 10–89",
    "Spain, 10–94",
    "Spain, 10–99",
    "Spain half-age, 10–99",
    "Madrid approximation, 10–94",
]
axes[1].barh(
    labels,
    [s["residual"] / 1000 for s in variants],
    color=["#2d737b"] * 4 + ["#bc7743"],
)
axes[1].set(
    xlabel="Residual, thousand people", title="Mortality and endpoint-age scenarios"
)
axes[1].invert_yaxis()
axes[1].grid(axis="x", alpha=0.15)
fig.suptitle(
    "Madrid: observed research validation (not official statistics)", fontsize=12
)
fig.text(
    0.02,
    0.01,
    "2021 uses explicit monthly-bank city counts after a 34,170-person raw-source discrepancy. Scenarios are not confidence intervals.",
    fontsize=8,
)
fig.tight_layout(rect=[0, 0.03, 1, 0.95])
fig.savefig(ROOT / "reports/research-validation.pdf")
fig.savefig(ROOT / "reports/research-validation.png", dpi=160)
print("Wrote research report and validation plots")
