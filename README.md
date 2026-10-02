# Madrid demographic residual

A reproducible offline cohort-survival pipeline and static explorer for Madrid, following [PLAN.md](PLAN.md). Source acquisition, normalization, geometry auditing, exact crosswalks, modeling, QA, Parquet/CSV export, sensitivity scenarios, and the explorer are implemented. **Official Madrid results are not yet available:** 29 source snapshots are pinned; empirical release gates still need resolution and review. See [implementation status](docs/IMPLEMENTATION.md).

The generated demonstration uses artificial counts, mortality schedules, and rectangular polygons. Both the website and manifests identify it as synthetic. Exact-only results are the default; their parent aggregates explicitly disclose subset coverage.

## Run

Use Python 3.12. In the prepared environment:

```bash
source .venv/bin/activate
python scripts/build_demo.py
python -m http.server 8000 -d web
```

Open <http://localhost:8000>. The explorer has no JavaScript build dependencies. Two demonstration windows, 2015–2025 and 2014–2024, support section zones, barrios, districts, city totals, age presets/custom ranges, quality filters, charts, tables, and downloads.

For a fresh checkout:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock
pip install --no-deps -e .
python scripts/build_demo.py
```

GDAL (`ogr2ogr`, tested with the installed GDAL CLI) is needed only to import official shapefile archives. Geometry overlay and analysis use Shapely and PyProj.

## Analytical workflow

```bash
python -m madrid_demography.cli acquire --lock sources.lock.yml --root data/raw
python -m madrid_demography.cli discover data/raw/RESOURCE_ID/CHECKSUM
python -m madrid_demography.cli normalize data/raw/RESOURCE_ID/CHECKSUM --schema REVIEWED_SCHEMA_ID --date 2015-01-01 --source-id RESOURCE_ID --output data/intermediate/padron_2015.csv
python -m madrid_demography.cli overlay --old data/intermediate/sections_2015.geojson --new data/intermediate/sections_2025.geojson --crs EPSG:25830 --output data/intermediate/boundary_audit
python -m madrid_demography.cli prepare config/project.json
python -m madrid_demography.cli build config/project.json
```

These commands require real input files and a completed project configuration; source snapshots are pinned, while the model-facing example configuration and schema aliases still require completion. Acquisition never automatically approves a checksum or historical date. Instructions and all contracts are in [the data workflow](docs/DATA_WORKFLOW.md); [the configuration example](config/project.example.json) illustrates the build structure.

Official builds require pinned sources, reviewed January profiles, independent published totals, geometry and parent audits, independently reproduced survival chains, and checksum-bound review evidence. They fail closed on missing evidence, changed inputs, or failed invariants. Births and nationality corrections remain explicitly separate research scenarios, enabled only with supplied validated inputs.

## Official source audit

The acquired monthly January series, independent annual controls, mortality tables and geometry archives are documented in [SOURCE_AUDIT.md](docs/SOURCE_AUDIT.md) and [RECONCILIATION.md](docs/RECONCILIATION.md). Run the audit independently of the publication pipeline:

```bash
python -m madrid_demography.profile
python -m madrid_demography.reconcile
python -m madrid_demography.normalise
python scripts/check_official_inputs.py
```

`normalise` preserves nullable counts and exceptional geography in audit exports. These exports do not satisfy the model-facing `normalize` contract and cannot be published as official results. A separate [conditional blank-count policy](docs/BLANK_COUNT_POLICY.md) produces a labelled research candidate after checking 7,560 monthly controls. The [boundary review](docs/BOUNDARY_REVIEW.md) and [PDF atlas](reports/boundary-review-atlas.pdf) document changed sections and historical parent exceptions. See [integration status](docs/OFFICIAL_INTEGRATION.md).

## Verify

```bash
python -m unittest discover -s tests -v
python scripts/build_demo.py
python scripts/check_budgets.py
pip install -r requirements-test.lock
python scripts/check_browser.py
```

The browser script uses `/usr/bin/chromium` locally; set `MADRID_BROWSER=playwright` to use a Playwright-installed browser. It needs permission to launch Chromium and listen on localhost. CI runs analytical, fixture-budget, and browser checks. The manual official-build workflow acquires pinned resources, prepares canonical inputs, enforces release gates, and uploads artifacts without deploying them.

Generated window bundles and raw official data are excluded from Git; rebuild the demonstration after checkout. Hashed JSON/gzip artifacts permit immutable caching; catalog and manifest files require revalidation. See the generated `audit.html`, `reports/`, and manifest for QA, source hashes, code hashes, geometry versions, and payload sizes.
