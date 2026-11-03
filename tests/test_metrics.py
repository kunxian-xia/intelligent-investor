from __future__ import annotations

import sqlite3

from intelligent_investor.db import initialize
from intelligent_investor.metrics import configure_metric_pack, record_metric


def test_metric_pack_and_evidence_backed_observation() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize(connection)
    connection.execute(
        "INSERT INTO companies VALUES (?, ?, ?, ?)",
        ("1", "PBR", "Petrobras", "now"),
    )
    connection.execute(
        """INSERT INTO filings(
               accession_number, cik, ticker, form, filing_date, report_date,
               primary_document, source_url, is_xbrl
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("abc", "1", "PBR", "20-F", "2026-04-09", "2025-12-31", "report.htm", "https://example.com", 1),
    )
    connection.commit()

    assert configure_metric_pack(connection, "PBR", "upstream_oil") == 8
    record_metric(
        connection,
        ticker="PBR",
        metric_key="lifting_cost",
        period_end="2025-12-31",
        value=9.1,
        unit="USD/boe",
        accession_number="abc",
        scope={"geography": "Brazil", "includes_leases": True},
        evidence_text="Including leases, lifting cost was US$9.1 per boe.",
        source_locator="Operating performance / Lifting Cost",
    )
    row = connection.execute(
        """SELECT metric_key, value, unit, scope_json, evidence_text
           FROM operating_metric_observations"""
    ).fetchone()
    assert row["metric_key"] == "lifting_cost"
    assert row["value"] == 9.1
    assert row["scope_json"] == '{"geography":"Brazil","includes_leases":true}'
    assert "US$9.1" in row["evidence_text"]
    coverage = connection.execute(
        """SELECT observation_count, latest_period_end, metric_status
           FROM metric_coverage
           WHERE ticker = 'PBR' AND metric_key = 'lifting_cost'"""
    ).fetchone()
    assert tuple(coverage) == (1, "2025-12-31", "available")
    missing = connection.execute(
        """SELECT metric_status FROM metric_coverage
           WHERE ticker = 'PBR' AND metric_key = 'realized_oil_price'"""
    ).fetchone()
    assert missing[0] == "missing"
