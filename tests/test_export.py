from __future__ import annotations

import sqlite3

from intelligent_investor.db import initialize
from intelligent_investor.export import export_excel, sync_status


def test_export_revision_matches_database(tmp_path) -> None:
    database_path = tmp_path / "test.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    initialize(connection)
    workbook_path = tmp_path / "financials.xlsx"

    revision, _rows, digest = export_excel(connection, workbook_path)

    assert revision == 0
    assert len(digest) == 64
    assert sync_status(connection, workbook_path) == (True, 0, 0)
