# Research explorer publication and deployment

The generated website is a static research explorer with observed counts, three comparison datasets and explicit limitations. It must retain the research banner and closed official-release flags.

## GitHub publication

Implementation and evidence branch: `codex/integrate-official-source-audit`.

Website branch: `gh-pages`, root directory, with `.nojekyll`.

The integration branch contains `reports/research-explorer.zip`, which expands to the entire standalone website, plus `reports/current-audit.pdf`, validation plots, screenshots and the small-area inventory. Serve the extracted directory with a static HTTP server; opening index.html directly cannot load browser modules or JSON.

## Hosting setting required

In [repository Settings → Pages](https://github.com/danialmazan/population_change_espext_madrid/settings/pages), select **Deploy from a branch**, branch **gh-pages**, directory **/(root)**, and save.

Once GitHub reports a successful Pages deployment, the expected URL is https://danialmazan.github.io/population_change_espext_madrid/ . This is a target URL, not a claim that deployment has completed.

The available GitHub connector can publish repository content and pull requests, but has no Pages configuration operation. The environment has no configured GitHub API credential, and direct API access previously returned Forbidden. A live Pages URL cannot be checked through the current destination policy, which does not allow danialmazan.github.io. Hosting activation or a supported connection/policy configuration is therefore the remaining input dependency.

## Updating

Install Python 3.12 dependencies from requirements.lock and the audit-gis extra. Acquire the exact locked inputs, build with scripts/build_research.py, run scripts/check_research_budgets.py and scripts/check_research_browser.py, then update the gh-pages branch from data/derived/research-site. Keep full artifact and download checksums, research labels, source attribution, exceptional population accounting and the separate whole-city dataset.

Official statistical release is a separate evidence decision. Pages activation does not approve historical administrative boundaries, reconcile the 2021 source discrepancy, or provide empirical warning signoffs.
