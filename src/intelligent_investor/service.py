from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .db import revision_transaction
from .sec import Company, SecClient
from .taxonomy import classify_concept


FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A", "20-F", "20-F/A", "40-F"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def recent_filings(submissions: dict[str, Any]) -> Iterable[dict[str, Any]]:
    recent = submissions.get("filings", {}).get("recent", {})
    keys = (
        "accessionNumber",
        "filingDate",
        "reportDate",
        "form",
        "primaryDocument",
    )
    length = len(recent.get("accessionNumber", []))
    for index in range(length):
        row = {key: recent.get(key, [None] * length)[index] for key in keys}
        if row["form"] in FORMS and row["primaryDocument"]:
            yield row


def iter_facts(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for taxonomy, concepts in payload.get("facts", {}).items():
        for concept, details in concepts.items():
            for unit, observations in details.get("units", {}).items():
                for observation in observations:
                    if observation.get("form") not in FORMS:
                        continue
                    yield {
                        "taxonomy": taxonomy,
                        "concept": concept,
                        "label": details.get("label"),
                        "description": details.get("description"),
                        "unit": unit,
                        "value": observation.get("val"),
                        "start_date": observation.get("start"),
                        "end_date": observation.get("end"),
                        "filed_date": observation.get("filed"),
                        "fiscal_year": observation.get("fy"),
                        "fiscal_period": observation.get("fp"),
                        "form": observation.get("form"),
                        "accession_number": observation.get("accn"),
                        "frame": observation.get("frame"),
                    }


class RefreshService:
    def __init__(
        self, connection: sqlite3.Connection, sec: SecClient, filing_root: Path
    ) -> None:
        self.connection = connection
        self.sec = sec
        self.filing_root = filing_root

    def refresh(self, tickers: list[str], download_count: int = 4) -> int:
        collected: list[tuple[Company, dict[str, Any], dict[str, Any]]] = []
        for ticker in tickers:
            company = self.sec.resolve_ticker(ticker)
            collected.append(
                (company, self.sec.submissions(company.cik), self.sec.company_facts(company.cik))
            )

        now = utc_now()
        downloads: list[tuple[Company, dict[str, Any], Path]] = []
        with revision_transaction(self.connection) as revision:
            for company, submissions, facts_payload in collected:
                self.connection.execute(
                    """INSERT INTO companies(cik, ticker, name, updated_at)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(cik) DO UPDATE SET
                         ticker=excluded.ticker, name=excluded.name, updated_at=excluded.updated_at""",
                    (company.cik, company.ticker, company.name, now),
                )
                filings = list(recent_filings(submissions))
                for row in filings:
                    accession = row["accessionNumber"]
                    source_url = self._filing_url(company.cik, accession, row["primaryDocument"])
                    self.connection.execute(
                        """INSERT INTO filings(
                               accession_number, cik, ticker, form, filing_date, report_date,
                               primary_document, source_url
                           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(accession_number) DO UPDATE SET
                               form=excluded.form, filing_date=excluded.filing_date,
                               report_date=excluded.report_date, primary_document=excluded.primary_document,
                               source_url=excluded.source_url""",
                        (
                            accession,
                            company.cik,
                            company.ticker,
                            row["form"],
                            row["filingDate"],
                            row["reportDate"],
                            row["primaryDocument"],
                            source_url,
                        ),
                    )
                for row in filings[:download_count]:
                    destination = (
                        self.filing_root
                        / company.ticker
                        / row["accessionNumber"]
                        / row["primaryDocument"]
                    )
                    if not destination.exists():
                        downloads.append((company, row, destination))

                for fact in iter_facts(facts_payload):
                    statement, standardized_metric = classify_concept(
                        fact["taxonomy"], fact["concept"]
                    )
                    key_parts = (
                        company.cik,
                        fact["taxonomy"],
                        fact["concept"],
                        fact["unit"],
                        fact["start_date"] or "",
                        fact["end_date"] or "",
                        fact["filed_date"] or "",
                        fact["accession_number"] or "",
                        fact["frame"] or "",
                    )
                    observation_key = hashlib.sha256(
                        "\x1f".join(key_parts).encode("utf-8")
                    ).hexdigest()
                    self.connection.execute(
                        """INSERT INTO facts(
                               observation_key, cik, ticker, taxonomy, concept, statement,
                               standardized_metric, label, description, unit, value,
                               start_date, end_date, filed_date, fiscal_year, fiscal_period, form,
                               accession_number, frame
                           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(observation_key) DO UPDATE SET
                               value=excluded.value, label=excluded.label,
                               description=excluded.description,
                               statement=excluded.statement,
                               standardized_metric=excluded.standardized_metric""",
                        (
                            observation_key,
                            company.cik,
                            company.ticker,
                            fact["taxonomy"],
                            fact["concept"],
                            statement,
                            standardized_metric,
                            fact["label"],
                            fact["description"],
                            fact["unit"],
                            fact["value"],
                            fact["start_date"],
                            fact["end_date"],
                            fact["filed_date"],
                            fact["fiscal_year"],
                            fact["fiscal_period"],
                            fact["form"],
                            fact["accession_number"],
                            fact["frame"],
                        ),
                    )

        # Downloads occur after the database transaction; failures cannot corrupt facts.
        for company, row, destination in downloads:
            try:
                self.sec.download_filing(
                    company.cik,
                    row["accessionNumber"],
                    row["primaryDocument"],
                    destination,
                )
                self.connection.execute(
                    """UPDATE filings SET local_path = ?, downloaded_at = ?, download_error = NULL
                       WHERE accession_number = ?""",
                    (str(destination), utc_now(), row["accessionNumber"]),
                )
            except Exception as exc:
                self.connection.execute(
                    "UPDATE filings SET download_error = ? WHERE accession_number = ?",
                    (str(exc), row["accessionNumber"]),
                )
        self.connection.commit()
        return revision

    @staticmethod
    def _filing_url(cik: str, accession: str, document: str) -> str:
        return (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{accession.replace('-', '')}/{document}"
        )
