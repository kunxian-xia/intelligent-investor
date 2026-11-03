from __future__ import annotations

import sqlite3

from intelligent_investor.db import initialize
from intelligent_investor.metrics import (
    configure_metric_pack,
    derive_metric,
    record_metric,
    validate_metrics,
)


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


def metric_database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize(connection)
    connection.execute(
        "INSERT INTO companies VALUES (?, ?, ?, ?)", ("1", "PBR", "Petrobras", "now")
    )
    connection.execute(
        """INSERT INTO filings(accession_number, cik, ticker, form, filing_date,
               report_date, primary_document, source_url, is_xbrl)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("annual", "1", "PBR", "20-F", "2026-04-01", "2025-12-31",
         "report.htm", "https://example.com/report", 1),
    )
    connection.commit()
    return connection


def test_offshore_pack_derives_reserve_life_with_input_lineage() -> None:
    connection = metric_database()
    assert configure_metric_pack(connection, "PBR", "offshore_ep") > 8
    scope = {"interest_basis": "net", "product": "boe"}
    record_metric(connection, ticker="PBR", metric_key="proved_reserves",
                  period_end="2025-12-31", value=1000, unit="million boe",
                  accession_number="annual", scope=scope)
    record_metric(connection, ticker="PBR", metric_key="production",
                  period_end="2025-12-31", value=200, unit="thousand boe/day",
                  accession_number="annual", scope=scope)

    derive_metric(connection, ticker="PBR", metric_key="reserve_life",
                  period_end="2025-12-31", scope=scope)

    result = connection.execute(
        """SELECT id, value, value_status, calculation_json
           FROM operating_metric_observations WHERE metric_key='reserve_life'"""
    ).fetchone()
    assert round(result["value"], 3) == 13.699
    assert result["value_status"] == "derived"
    assert connection.execute(
        "SELECT count(*) FROM metric_calculation_inputs WHERE derived_observation_id=?",
        (result["id"],),
    ).fetchone()[0] == 2


def test_validation_flags_missing_scope_and_impossible_percentage() -> None:
    connection = metric_database()
    configure_metric_pack(connection, "PBR", "offshore_ep")
    record_metric(connection, ticker="PBR", metric_key="water_cut",
                  period_end="2025-12-31", value=120, unit="%",
                  accession_number="annual", scope={})

    assert validate_metrics(connection, "PBR") == 2
    rules = {row[0] for row in connection.execute(
        "SELECT rule_key FROM metric_quality_issues"
    )}
    assert rules == {"missing_scope:asset", "outside_plausible_range"}


def test_derivation_rejects_incompatible_units() -> None:
    connection = metric_database()
    configure_metric_pack(connection, "PBR", "offshore_ep")
    scope = {"interest_basis": "net", "product": "boe"}
    record_metric(connection, ticker="PBR", metric_key="proved_reserves",
                  period_end="2025-12-31", value=1000, unit="million boe",
                  accession_number="annual", scope=scope)
    record_metric(connection, ticker="PBR", metric_key="production",
                  period_end="2025-12-31", value=200000, unit="boe/day",
                  accession_number="annual", scope=scope)
    try:
        derive_metric(connection, ticker="PBR", metric_key="reserve_life",
                      period_end="2025-12-31", scope=scope)
    except ValueError as exc:
        assert "must use thousand boe/day" in str(exc)
    else:
        raise AssertionError("incompatible input unit was accepted")
