from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .db import revision_transaction


UPSTREAM_OIL_METRICS = {
    "proved_reserves": {
        "display_name": "Total proved reserves",
        "description": "Year-end proved developed and undeveloped oil and gas reserves.",
        "default_unit": "million boe",
        "cadence": "annual",
        "preferred_direction": "higher",
    },
    "reserve_replacement_ratio": {
        "display_name": "Reserve replacement ratio",
        "description": "Proved reserve additions divided by production for the period.",
        "default_unit": "%",
        "cadence": "annual",
        "preferred_direction": "higher",
    },
    "reserve_life": {
        "display_name": "Reserve life",
        "description": "Proved reserves divided by annual production at the current rate.",
        "default_unit": "years",
        "cadence": "annual",
        "preferred_direction": "higher",
    },
    "production": {
        "display_name": "Oil and gas production",
        "description": "Average daily production, with geography and product in observation scope.",
        "default_unit": "thousand boe/day",
        "cadence": "quarterly",
        "preferred_direction": "contextual",
    },
    "upstream_capex": {
        "display_name": "Upstream capital expenditure",
        "description": "Capital expenditure attributable to exploration and production.",
        "default_unit": "USD million",
        "cadence": "quarterly",
        "preferred_direction": "contextual",
    },
    "realized_oil_price": {
        "display_name": "Realized oil price",
        "description": "Average realized sales price for crude oil, before or after hedging as scoped.",
        "default_unit": "USD/bbl",
        "cadence": "quarterly",
        "preferred_direction": "higher",
    },
    "realized_gas_price": {
        "display_name": "Realized natural gas price",
        "description": "Average realized sales price for natural gas, with basis stated in scope.",
        "default_unit": "USD/boe",
        "cadence": "quarterly",
        "preferred_direction": "higher",
    },
    "lifting_cost": {
        "display_name": "Lifting cost",
        "description": "Unit cost to operate and maintain producing assets; lease treatment in scope.",
        "default_unit": "USD/boe",
        "cadence": "quarterly",
        "preferred_direction": "lower",
    },
}


METRIC_PACKS = {"upstream_oil": UPSTREAM_OIL_METRICS}


def seed_metric_definitions(connection: sqlite3.Connection) -> None:
    for pack, metrics in METRIC_PACKS.items():
        for metric_key, definition in metrics.items():
            connection.execute(
                """INSERT INTO operating_metric_definitions(
                       metric_key, metric_pack, display_name, description, default_unit,
                       cadence, preferred_direction, definition_version
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(metric_key) DO UPDATE SET
                       metric_pack=excluded.metric_pack,
                       display_name=excluded.display_name,
                       description=excluded.description,
                       default_unit=excluded.default_unit,
                       cadence=excluded.cadence,
                       preferred_direction=excluded.preferred_direction,
                       definition_version=excluded.definition_version""",
                (
                    metric_key,
                    pack,
                    definition["display_name"],
                    definition["description"],
                    definition["default_unit"],
                    definition["cadence"],
                    definition["preferred_direction"],
                    "1.0",
                ),
            )


def configure_metric_pack(
    connection: sqlite3.Connection, ticker: str, metric_pack: str
) -> int:
    if metric_pack not in METRIC_PACKS:
        raise ValueError(f"Unknown metric pack: {metric_pack}")
    count = 0
    for metric_key in METRIC_PACKS[metric_pack]:
        connection.execute(
            """INSERT INTO company_metric_config(ticker, metric_key, enabled)
               VALUES (?, ?, 1)
               ON CONFLICT(ticker, metric_key) DO UPDATE SET enabled=1""",
            (ticker.upper(), metric_key),
        )
        count += 1
    connection.commit()
    return count


def record_metric(
    connection: sqlite3.Connection,
    *,
    ticker: str,
    metric_key: str,
    period_end: str,
    value: float,
    unit: str,
    accession_number: str,
    period_start: str | None = None,
    period_type: str = "annual",
    scope: dict[str, Any] | None = None,
    evidence_text: str | None = None,
    source_locator: str | None = None,
    extraction_method: str = "curated",
    confidence: float = 1.0,
) -> int:
    definition = connection.execute(
        "SELECT definition_version FROM operating_metric_definitions WHERE metric_key = ?",
        (metric_key,),
    ).fetchone()
    if definition is None:
        raise ValueError(f"Unknown operating metric: {metric_key}")
    filing = connection.execute(
        """SELECT filing_date, source_url FROM filings
           WHERE accession_number = ? AND ticker = ?""",
        (accession_number, ticker.upper()),
    ).fetchone()
    if filing is None:
        raise ValueError(f"Filing not found for {ticker}: {accession_number}")
    scope_json = json.dumps(scope or {}, sort_keys=True, separators=(",", ":"))
    with revision_transaction(connection) as revision:
        connection.execute(
            """INSERT INTO operating_metric_observations(
               ticker, metric_key, period_start, period_end, period_type, value, unit,
               scope_json, accession_number, filed_date, source_url, evidence_text,
               source_locator, extraction_method, confidence, definition_version,
               inserted_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(ticker, metric_key, period_end, scope_json, accession_number)
           DO UPDATE SET
               value=excluded.value, unit=excluded.unit,
               evidence_text=excluded.evidence_text,
               source_locator=excluded.source_locator,
               extraction_method=excluded.extraction_method,
               confidence=excluded.confidence,
               inserted_at=excluded.inserted_at""",
            (
                ticker.upper(),
                metric_key,
                period_start,
                period_end,
                period_type,
                value,
                unit,
                scope_json,
                accession_number,
                filing["filing_date"],
                filing["source_url"],
                evidence_text,
                source_locator,
                extraction_method,
                confidence,
                definition["definition_version"],
                datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            ),
        )
    return revision
