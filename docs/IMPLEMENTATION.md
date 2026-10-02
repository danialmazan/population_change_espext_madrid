# Implementation and validation status

Current observed research calculations, annual reconciliation, sensitivity checks and explorer results are documented in [RESEARCH_RESULTS.md](RESEARCH_RESULTS.md). Those calculations do not constitute an official release approval. Earlier acquisition audit sections below retain their recorded snapshot counts; the current lock additionally includes the archived INE reuse terms (41 pinned resources).

The original “research only” status in PLAN.md was obsolete. The repository now implements the software stages below. This does **not** assert completion of the plan's empirical research, source audits, or release gates.

| Phase | Software delivered | Remaining empirical work |
|---|---|---|
| 0: sources and feasibility | Immutable downloads and receipts; catalogue discovery; dated schema profiles; annual jump diagnostics; projected geometry overlap graph; split/merge/redraw classification; stable-zone crosswalk; topology, parent nesting and coverage checks; feasibility report | January 2014–2025 acquired/profiled; confirm historical resource/date semantics and GIS vintages; resolve licences; review every changed component; determine actual exact population coverage |
| 1: analytical MVP | Validated canonical facts; exact aggregation; annual age/sex cohort survival; sex/nationality detail; additive hierarchy; residuals/counts/rates; denominator suppression; terminal/birth exclusions; published-total reconciliation; machine QA; Parquet/CSV downloads | Reconcile official barrio/district/city controls; verify mortality dimensions/coverage and independently reproduce chains from life tables; select terminal age and sparse-denominator threshold from real distributions |
| 2: explorer | Four geography levels; TopoJSON map; combined rate default; exact-only and inclusive tiers; comparison windows; age presets/custom ranges; observed/expected and residual charts; nationality composition; tables, downloads and persistent quality; hashed lazy profiles; request cancellation; build manifests and CI budgets | Profile real payloads and set measured production budgets; no official release or hosting deployment has been made |
| 3: robustness | Half-age variant; configurable mortality schedules; intermediate-year diagnostics; temporally reviewed residential-capacity allocation and area-weight sensitivity API; quality/denominator suppression; alternate windows | Supply Spain and fallback mortality schedules; review allocation evidence and uncertainty; run real terminal-age and intermediate-year diagnostics; validate the alternate comparison |
| 4: optional research | Total-only projected births from surviving baseline women and explicit ASFR/1000; uniform birth timing/sex ratio; low/base/high nationality-hazard scenarios with depleted exposure and total cancellation | Validate fertility, births, nationality hazards and usefulness before public display; richer origin/country-of-birth views require new disclosure-approved source contracts and remain deferred |

## Current official input status

The earlier network blocker has been cleared. The source lock now pins 40 acquired snapshots, including January 2014–2025 files and both endpoint geometry archives. The empirical audit, independent controls and remaining release blockers are recorded in [OFFICIAL_INTEGRATION.md](OFFICIAL_INTEGRATION.md). Acquisition review is not an analytical release approval.

## Validation

The earlier software validation covered 29 Python tests, formatting/lint checks, four fixture payload-budget/checksum checks, and configuration parsing passed locally.

The browser smoke check passed for all four geography levels, keyboard selection, custom/preset ages, births exclusion, reliability tiers, comparison windows and mobile overflow.

The automated suite covers annual compounding, source/schema drift, mortality units and `l_x` ratios, missing/nonfinite mortality, nationality cancellation, hierarchy arithmetic, birth/terminal exclusions, sparse rate suppression, mixed-grain double counting, split/merge stable zones, changed-parent rejection, source overlap detection, fractional-weight contracts, capacity-allocation sensitivity, research scenarios, blocked official exports, deterministic artifacts and the configured end-to-end build.

The fixture build checks four bundles (two periods × exact/inclusive), including combined initial-data gzip <500 KB, per-level geometry gzip <1 MB, and area-profile gzip <100 KB. Fixture compliance does not establish real-data performance.

Review gates are evidence-driven. An official source flag alone cannot bypass them. The plan's 95% gate chooses whether section results are a suitable default; it does not justify suppressing accounting discrepancies or unreviewed changes.

## Completed research roadmap — 2 October 2026

City calculations for both ten-year windows, independent lx checks, national/Madrid and terminal-age sensitivities, intermediate-year comparisons, common-zone and parent pooling, and results at every spatial level are complete as research outputs. The 2021 raw-source discrepancy remains explicitly unresolved; its city comparison uses the monthly bank’s explicit counts. Historical parent validity and final analytical approvals remain official-release blockers.

The observed explorer passes real-data payload budgets and browser checks. The updated report, small-area inventory, plots, preview screenshots and website archive are published on the integration branch. A static gh-pages branch is prepared for GitHub Pages; the repository hosting setting must point to that branch before a live URL can be asserted.
