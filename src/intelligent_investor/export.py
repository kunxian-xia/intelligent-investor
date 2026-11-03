from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from .db import current_revision


TABLES = {
    "Data Quality": "SELECT * FROM data_quality ORDER BY ticker",
    "Companies": "SELECT * FROM companies ORDER BY ticker",
    "Feeds": "SELECT * FROM feeds ORDER BY name",
    "Filings": "SELECT * FROM filings ORDER BY ticker, filing_date DESC",
    "Standardized Financials": """SELECT ticker, statement, standardized_metric, value,
                                          unit, start_date, end_date, filed_date,
                                          fiscal_year, fiscal_period, form,
                                          accession_number, concept
                                   FROM facts
                                   WHERE standardized_metric IS NOT NULL
                                   ORDER BY ticker, statement, standardized_metric,
                                            end_date DESC, filed_date DESC""",
    "Financial Facts": """SELECT ticker, taxonomy, concept, label, unit, value,
                                  start_date, end_date, filed_date, fiscal_year,
                                  fiscal_period, form, accession_number, frame
                           FROM facts
                           ORDER BY ticker, concept, end_date DESC""",
    "Latest Sources": "SELECT * FROM source_items ORDER BY published_at DESC",
}


def _format_sheet(sheet) -> None:
    fill = PatternFill("solid", fgColor="1F4E78")
    for cell in sheet[1]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = fill
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for column in sheet.columns:
        values = [str(cell.value or "") for cell in list(column)[:200]]
        width = min(max(max(map(len, values), default=0) + 2, 10), 42)
        sheet.column_dimensions[get_column_letter(column[0].column)].width = width


def export_excel(connection: sqlite3.Connection, path: Path) -> tuple[int, int, str]:
    # Keep every worksheet on one SQLite read snapshot, even if another process
    # refreshes the database while this workbook is being assembled.
    connection.execute("BEGIN")
    try:
        revision = current_revision(connection)
        workbook = Workbook(write_only=False)
        state = workbook.active
        state.title = "Sync State"
        exported_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        state.append(["Property", "Value"])
        state.append(["Data revision", revision])
        state.append(["Exported at (UTC)", exported_at])
        state.append(
            ["Database", str(connection.execute("PRAGMA database_list").fetchone()[2])]
        )
        _format_sheet(state)

        row_count = 0
        for name, query in TABLES.items():
            sheet = workbook.create_sheet(name)
            cursor = connection.execute(query)
            headers = [item[0] for item in cursor.description]
            sheet.append(headers)
            for row in cursor:
                sheet.append(list(row))
                row_count += 1
            _format_sheet(sheet)
        connection.commit()
    except Exception:
        connection.rollback()
        raise

    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(suffix=".xlsx", dir=path.parent)
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        workbook.save(temporary)
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()

    connection.execute(
        """INSERT INTO exports(path, data_revision, exported_at, row_count, sha256)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(path) DO UPDATE SET
             data_revision=excluded.data_revision, exported_at=excluded.exported_at,
             row_count=excluded.row_count, sha256=excluded.sha256""",
        (str(path), revision, exported_at, row_count, digest),
    )
    connection.commit()
    return revision, row_count, digest


def excel_revision(path: Path) -> int:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        return int(workbook["Sync State"]["B2"].value)
    finally:
        workbook.close()


def sync_status(connection: sqlite3.Connection, path: Path) -> tuple[bool, int, int | None]:
    database_revision = current_revision(connection)
    if not path.exists():
        return False, database_revision, None
    workbook_revision = excel_revision(path)
    return database_revision == workbook_revision, database_revision, workbook_revision
