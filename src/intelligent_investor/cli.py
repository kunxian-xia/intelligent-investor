from __future__ import annotations

import argparse
import sys

from .config import load_settings, require_sec_identity
from .db import connect, initialize
from .export import export_excel, sync_status
from .feeds import FeedService
from .metrics import METRIC_PACKS, configure_metric_pack
from .sec import SecClient
from .service import RefreshService


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(prog="investor")
    subcommands = command.add_subparsers(dest="command", required=True)

    init = subcommands.add_parser("init", help="Create the local database")
    init.set_defaults(handler=run_init)

    refresh = subcommands.add_parser("refresh", help="Refresh SEC data and Excel")
    refresh.add_argument("tickers", nargs="+", help="US ticker symbols, such as AAPL MSFT")
    refresh.add_argument(
        "--download-count",
        type=int,
        default=4,
        help="Recent annual/quarterly reports to keep locally per company",
    )
    refresh.set_defaults(handler=run_refresh)

    export = subcommands.add_parser("export", help="Regenerate Excel from SQLite")
    export.set_defaults(handler=run_export)

    status = subcommands.add_parser("status", help="Check SQLite/Excel synchronization")
    status.set_defaults(handler=run_status)

    add_feed = subcommands.add_parser("add-feed", help="Add an RSS or Atom information source")
    add_feed.add_argument("name", help="A stable source name")
    add_feed.add_argument("url", help="RSS or Atom URL")
    add_feed.add_argument("--ticker", help="Optional ticker associated with every feed item")
    add_feed.set_defaults(handler=run_add_feed)

    refresh_feeds = subcommands.add_parser(
        "refresh-feeds", help="Pull configured RSS/Atom sources and export Excel"
    )
    refresh_feeds.set_defaults(handler=run_refresh_feeds)

    configure = subcommands.add_parser(
        "configure-metrics", help="Enable a sector operating-metric pack for a company"
    )
    configure.add_argument("ticker")
    configure.add_argument("metric_pack", choices=sorted(METRIC_PACKS))
    configure.set_defaults(handler=run_configure_metrics)
    return command


def database():
    settings = load_settings()
    connection = connect(settings.database_path)
    initialize(connection)
    return settings, connection


def run_init(_args: argparse.Namespace) -> int:
    settings, connection = database()
    connection.close()
    print(f"Initialized {settings.database_path}")
    return 0


def run_refresh(args: argparse.Namespace) -> int:
    settings, connection = database()
    require_sec_identity(settings)
    try:
        service = RefreshService(
            connection, SecClient(settings.user_agent), settings.filing_dir
        )
        revision = service.refresh(
            [ticker.upper() for ticker in args.tickers], args.download_count
        )
        _, rows, _ = export_excel(connection, settings.excel_path)
        print(
            f"Refresh complete: revision {revision}, {rows} Excel rows, "
            f"{settings.excel_path}"
        )
        return 0
    finally:
        connection.close()


def run_export(_args: argparse.Namespace) -> int:
    settings, connection = database()
    try:
        revision, rows, _ = export_excel(connection, settings.excel_path)
        print(f"Exported revision {revision} ({rows} rows) to {settings.excel_path}")
        return 0
    finally:
        connection.close()


def run_status(_args: argparse.Namespace) -> int:
    settings, connection = database()
    try:
        synced, database_revision, workbook_revision = sync_status(
            connection, settings.excel_path
        )
        state = "IN SYNC" if synced else "STALE"
        print(
            f"{state}: SQLite revision={database_revision}, "
            f"Excel revision={workbook_revision}"
        )
        return 0 if synced else 2
    finally:
        connection.close()


def run_add_feed(args: argparse.Namespace) -> int:
    settings, connection = database()
    try:
        FeedService(connection, settings.user_agent).add(args.name, args.url, args.ticker)
        print(f"Added feed {args.name}: {args.url}")
        return 0
    finally:
        connection.close()


def run_refresh_feeds(_args: argparse.Namespace) -> int:
    settings, connection = database()
    try:
        revision, count = FeedService(connection, settings.user_agent).refresh()
        _, rows, _ = export_excel(connection, settings.excel_path)
        print(f"Feed refresh complete: revision {revision}, {count} items, {rows} Excel rows")
        return 0
    finally:
        connection.close()


def run_configure_metrics(args: argparse.Namespace) -> int:
    settings, connection = database()
    try:
        count = configure_metric_pack(connection, args.ticker, args.metric_pack)
        export_excel(connection, settings.excel_path)
        print(f"Enabled {count} {args.metric_pack} metrics for {args.ticker.upper()}")
        return 0
    finally:
        connection.close()


def main() -> None:
    try:
        arguments = parser().parse_args()
        raise SystemExit(arguments.handler(arguments))
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
