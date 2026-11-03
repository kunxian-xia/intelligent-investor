from __future__ import annotations

import sqlite3
from pathlib import Path

from intelligent_investor.db import current_revision, initialize, revision_transaction
from intelligent_investor.sec import Company
from intelligent_investor.service import RefreshService, iter_facts, recent_filings
from intelligent_investor.taxonomy import classify_concept


def memory_database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize(connection)
    return connection


def test_revision_transaction_commits_once() -> None:
    connection = memory_database()
    with revision_transaction(connection) as revision:
        assert revision == 1
    assert current_revision(connection) == 1


def test_initialize_adds_new_columns_to_existing_database() -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute("INSERT INTO metadata VALUES ('data_revision', '0')")
    connection.execute("CREATE TABLE companies(cik TEXT PRIMARY KEY, ticker TEXT, name TEXT, updated_at TEXT)")
    connection.execute(
        """CREATE TABLE filings(
               accession_number TEXT PRIMARY KEY, cik TEXT, ticker TEXT, form TEXT,
               filing_date TEXT, report_date TEXT, primary_document TEXT,
               source_url TEXT, local_path TEXT, downloaded_at TEXT)"""
    )
    connection.execute(
        """CREATE TABLE facts(
               id INTEGER PRIMARY KEY, cik TEXT, ticker TEXT, taxonomy TEXT,
               concept TEXT, label TEXT, description TEXT, unit TEXT, value REAL,
               start_date TEXT, end_date TEXT, filed_date TEXT, fiscal_year INTEGER,
               fiscal_period TEXT, form TEXT, accession_number TEXT, frame TEXT)"""
    )
    initialize(connection)
    fact_columns = {row[1] for row in connection.execute("PRAGMA table_info(facts)")}
    filing_columns = {row[1] for row in connection.execute("PRAGMA table_info(filings)")}
    assert {"observation_key", "statement", "standardized_metric"} <= fact_columns
    assert "download_error" in filing_columns


def test_revision_transaction_rolls_back() -> None:
    connection = memory_database()
    try:
        with revision_transaction(connection):
            connection.execute(
                "INSERT INTO companies VALUES (?, ?, ?, ?)",
                ("1", "TEST", "Test", "now"),
            )
            raise RuntimeError("stop")
    except RuntimeError:
        pass
    assert current_revision(connection) == 0
    assert connection.execute("SELECT count(*) FROM companies").fetchone()[0] == 0


def test_recent_filings_filters_forms() -> None:
    payload = {
        "filings": {
            "recent": {
                "accessionNumber": ["a", "b", "c"],
                "filingDate": ["2024-01-01"] * 3,
                "reportDate": ["2023-12-31"] * 3,
                "form": ["10-K", "8-K", "10-Q"],
                "primaryDocument": ["a.htm", "b.htm", "c.htm"],
            }
        }
    }
    assert [item["accessionNumber"] for item in recent_filings(payload)] == ["a", "c"]


def test_iter_facts_preserves_financial_context() -> None:
    payload = {
        "facts": {
            "us-gaap": {
                "Revenue": {
                    "label": "Revenue",
                    "description": "Sales",
                    "units": {
                        "USD": [
                            {
                                "val": 10,
                                "start": "2023-01-01",
                                "end": "2023-12-31",
                                "filed": "2024-02-01",
                                "form": "10-K",
                                "fy": 2023,
                                "fp": "FY",
                                "accn": "abc",
                            },
                            {"val": 11, "form": "8-K"},
                        ]
                    },
                }
            }
        }
    }
    rows = list(iter_facts(payload))
    assert len(rows) == 1
    assert rows[0]["unit"] == "USD"
    assert rows[0]["accession_number"] == "abc"


def test_common_us_gaap_concept_is_standardized() -> None:
    assert classify_concept("us-gaap", "Assets") == ("balance_sheet", "total_assets")
    assert classify_concept("custom", "Assets") == (None, None)


def test_refresh_stores_filing_and_standardized_fact(tmp_path) -> None:
    class FakeSec:
        def resolve_ticker(self, ticker):
            return Company("0000000001", ticker, "Test Company")

        def submissions(self, _cik):
            return {
                "filings": {
                    "recent": {
                        "accessionNumber": ["0001-24-000001"],
                        "filingDate": ["2024-02-01"],
                        "reportDate": ["2023-12-31"],
                        "form": ["10-K"],
                        "primaryDocument": ["report.htm"],
                    }
                }
            }

        def company_facts(self, _cik):
            return {
                "facts": {
                    "us-gaap": {
                        "Assets": {
                            "label": "Assets",
                            "description": "Total assets",
                            "units": {
                                "USD": [
                                    {
                                        "val": 100,
                                        "end": "2023-12-31",
                                        "filed": "2024-02-01",
                                        "form": "10-K",
                                        "fy": 2023,
                                        "fp": "FY",
                                        "accn": "0001-24-000001",
                                    }
                                ]
                            },
                        }
                    }
                }
            }

        def download_filing(self, _cik, _accession, _document, destination):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text("report")

    connection = memory_database()
    revision = RefreshService(connection, FakeSec(), tmp_path).refresh(["TEST"], 1)
    row = connection.execute(
        "SELECT standardized_metric, value FROM facts"
    ).fetchone()

    assert revision == 1
    assert tuple(row) == ("total_assets", 100)
    assert connection.execute("SELECT count(*) FROM filings").fetchone()[0] == 1
