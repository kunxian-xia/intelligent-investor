# Intelligent Investor

A local-first collector for US public-company filings and financial statement data.
It uses official SEC EDGAR endpoints, keeps SQLite as the source of truth, downloads
recent annual and quarterly reports, and creates a revision-matched Excel snapshot.

## What the first version does

- Resolves US ticker symbols to SEC CIK identifiers.
- Collects 10-K, 10-Q, 20-F, and 40-F filing metadata.
- Downloads the latest filing documents to `data/filings/`.
- Stores every SEC XBRL observation with its unit, period, form, accession number,
  fiscal year, and filing date. Restatements remain distinguishable.
- Maps a conservative set of common US-GAAP concepts into income statement,
  balance sheet, and cash-flow metrics while retaining the original concepts.
- Supports IFRS foreign private issuers such as Petrobras, including XBRL-tagged
  interim 6-K filings while excluding ordinary 6-K news announcements.
- Publishes a `data_quality` view and Excel worksheet that flag when SEC's
  aggregate company-facts feed trails a newer structured filing.
- Exports companies, filings, facts, and source items to `data/financials.xlsx`.
- Writes the same data revision to SQLite and Excel and reports when Excel is stale.

## Setup

Python 3.11 or later is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
cp .env.example .env
```

Load the environment variables from `.env`, or set them in your shell. The SEC
requires automated clients to identify themselves with a real contact address:

```bash
export SEC_USER_AGENT="IntelligentInvestor your-email@example.com"
export INVESTOR_DATA_DIR="./data"
```

## Use

Initialize an empty database:

```bash
investor init
```

Refresh one or more companies. This commits the SQLite revision first and then
creates the matching Excel snapshot:

```bash
investor refresh AAPL MSFT --download-count 4
```

Check whether the workbook represents the current database revision:

```bash
investor status
```

Regenerate a stale or deleted workbook without contacting the SEC:

```bash
investor export
```

Add company investor-relations, SEC, macroeconomic, or licensed news RSS/Atom feeds,
then pull their latest items into SQLite and the `Latest Sources` worksheet:

```bash
investor add-feed apple-ir "https://example.com/apple-investor-relations.xml" --ticker AAPL
investor add-feed sec-updates "https://example.com/sec-updates.xml"
investor refresh-feeds
```

Enable a sector-specific operating KPI pack. Unlike generic financial facts, these
observations retain metric definitions, scope, filing evidence, extraction method,
and confidence for reliable model use:

```bash
investor configure-metrics PBR offshore_ep
investor configure-metrics EOG shale_ep
```

The `offshore_ep` pack adds FPSO throughput, capacity, utilization and uptime,
water cut, production efficiency, lost production, project schedule/cost variance,
field netback, and decommissioning obligations. The `shale_ep` pack instead adds
base decline, wells turned to sales, well cost, IP90, normalized EUR, economic
locations, and maintenance capital. Shared reserve, production, price, cost, and
capex metrics remain defined once.

Each observation must say whether it is `reported`, `derived`, or `estimated`.
Reported values retain the filing accession, source URL, locator, evidence text,
scope, and confidence. Derived values are calculated only from observations with
the exact same period and scope. The calculation and every input observation ID
are saved for audit.

For example, after recording proved reserves and average daily production with the
same scope, calculate reserve life deterministically:

```bash
investor derive-metric PBR reserve_life 2025-12-31 \
  --scope '{"interest_basis":"net","product":"boe"}'
```

The calculator rejects missing inputs and incompatible units instead of silently
converting ambiguous disclosures. Available deterministic calculations are reserve
life, reserve replacement ratio, and FPSO utilization.

Run data-quality checks after loading observations:

```bash
investor validate-metrics --ticker PBR
```

Checks currently cover required scope fields, plausible percentage ranges, and
calculation lineage. Results are written to `metric_quality_issues` and the
`Metric Quality Issues` Excel worksheet. A nonzero issue count returns exit code 2
so scheduled jobs can route the data to review before model use.

Use the actual feed URLs published by each source. Keeping these configurable avoids
embedding an unstable URL or assuming redistribution rights for commercial news.

## Data ownership and synchronization

SQLite is authoritative. Do not edit the generated workbook as a data-entry file;
it is replaced on export. Keep valuation models and personal notes in a separate
workbook that imports or references the exported tables.

Each successful data refresh advances `metadata.data_revision` in the database.
The Excel workbook stores that value in `Sync State!B2`. `investor status` compares
the two values. The export is written to a temporary file and atomically renamed,
so an interrupted export cannot leave a partially written workbook.

## Scheduling

Once a manual refresh works, schedule the same command with `cron`, `launchd`, or
another job runner. A daily refresh is normally enough because EDGAR data updates
when companies file, not continuously with market prices.

## Current boundaries

This version preserves SEC concepts exactly and adds a conservative standardized
view for common metrics. Company-specific extension concepts remain in the raw
`facts` table and may need explicit mappings before they appear in the standardized
view. The raw observation always remains available for audit.

RSS and Atom sources populate `source_items` and the `Latest Sources` workbook sheet.
Sources without feeds need separate adapters and, in some cases, API keys or
licensing decisions.
