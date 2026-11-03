from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO metadata(key, value) VALUES ('data_revision', '0');

CREATE TABLE IF NOT EXISTS companies (
    cik TEXT PRIMARY KEY,
    ticker TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS filings (
    accession_number TEXT PRIMARY KEY,
    cik TEXT NOT NULL REFERENCES companies(cik),
    ticker TEXT NOT NULL,
    form TEXT NOT NULL,
    filing_date TEXT NOT NULL,
    report_date TEXT,
    primary_document TEXT,
    source_url TEXT NOT NULL,
    local_path TEXT,
    downloaded_at TEXT,
    download_error TEXT,
    UNIQUE(cik, accession_number)
);

CREATE INDEX IF NOT EXISTS idx_filings_ticker_date
ON filings(ticker, filing_date DESC);

CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY,
    observation_key TEXT NOT NULL UNIQUE,
    cik TEXT NOT NULL REFERENCES companies(cik),
    ticker TEXT NOT NULL,
    taxonomy TEXT NOT NULL,
    concept TEXT NOT NULL,
    statement TEXT,
    standardized_metric TEXT,
    label TEXT,
    description TEXT,
    unit TEXT NOT NULL,
    value REAL,
    start_date TEXT,
    end_date TEXT,
    filed_date TEXT,
    fiscal_year INTEGER,
    fiscal_period TEXT,
    form TEXT,
    accession_number TEXT,
    frame TEXT
);

CREATE INDEX IF NOT EXISTS idx_facts_lookup
ON facts(ticker, concept, end_date DESC);

CREATE TABLE IF NOT EXISTS feeds (
    name TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    ticker TEXT,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1))
);

CREATE TABLE IF NOT EXISTS source_items (
    id INTEGER PRIMARY KEY,
    source_name TEXT NOT NULL,
    external_id TEXT NOT NULL,
    ticker TEXT,
    title TEXT NOT NULL,
    published_at TEXT,
    url TEXT NOT NULL,
    summary TEXT,
    fetched_at TEXT NOT NULL,
    UNIQUE(source_name, external_id)
);

CREATE TABLE IF NOT EXISTS exports (
    path TEXT PRIMARY KEY,
    data_revision INTEGER NOT NULL,
    exported_at TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    sha256 TEXT NOT NULL
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)
    # Small additive migrations keep local databases usable as the schema evolves.
    _ensure_column(connection, "filings", "download_error", "TEXT")
    _ensure_column(connection, "facts", "observation_key", "TEXT")
    _ensure_column(connection, "facts", "statement", "TEXT")
    _ensure_column(connection, "facts", "standardized_metric", "TEXT")
    connection.execute(
        "UPDATE facts SET observation_key = 'legacy-' || id WHERE observation_key IS NULL"
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_facts_observation_key ON facts(observation_key)"
    )
    connection.execute(
        """CREATE INDEX IF NOT EXISTS idx_standard_facts_lookup
           ON facts(ticker, standardized_metric, end_date DESC)"""
    )
    connection.commit()


def _ensure_column(
    connection: sqlite3.Connection, table: str, column: str, definition: str
) -> None:
    existing = {
        row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in existing:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


@contextmanager
def revision_transaction(connection: sqlite3.Connection) -> Iterator[int]:
    """Commit an entire refresh atomically and advance its revision once."""
    connection.execute("BEGIN IMMEDIATE")
    try:
        current = int(
            connection.execute(
                "SELECT value FROM metadata WHERE key = 'data_revision'"
            ).fetchone()[0]
        )
        next_revision = current + 1
        yield next_revision
        connection.execute(
            "UPDATE metadata SET value = ? WHERE key = 'data_revision'",
            (str(next_revision),),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def current_revision(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT value FROM metadata WHERE key = 'data_revision'"
    ).fetchone()
    return int(row[0])
