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
