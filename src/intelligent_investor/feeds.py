from __future__ import annotations

import hashlib
import sqlite3
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Iterable

from .db import revision_transaction


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(element: ET.Element, names: set[str]) -> str | None:
    for child in element:
        if _local_name(child.tag) in names and child.text:
            return child.text.strip()
    return None


def parse_feed(content: bytes) -> Iterable[dict[str, str | None]]:
    root = ET.fromstring(content)
    for element in root.iter():
        if _local_name(element.tag) not in {"item", "entry"}:
            continue
        title = _child_text(element, {"title"}) or "Untitled"
        url = _child_text(element, {"link"})
        if not url:
            for child in element:
                if _local_name(child.tag) == "link" and child.attrib.get("href"):
                    url = child.attrib["href"]
                    break
        if not url:
            continue
        external_id = _child_text(element, {"guid", "id"}) or url
        yield {
            "external_id": external_id,
            "title": title,
            "url": url,
            "published_at": _child_text(element, {"pubDate", "published", "updated"}),
            "summary": _child_text(element, {"description", "summary", "content"}),
        }


class FeedService:
    def __init__(self, connection: sqlite3.Connection, user_agent: str) -> None:
        self.connection = connection
        self.user_agent = user_agent

    def add(self, name: str, url: str, ticker: str | None = None) -> None:
        self.connection.execute(
            """INSERT INTO feeds(name, url, ticker) VALUES (?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET url=excluded.url, ticker=excluded.ticker,
                                               enabled=1""",
            (name, url, ticker.upper() if ticker else None),
        )
        self.connection.commit()

    def refresh(self) -> tuple[int, int]:
        fetched: list[tuple[sqlite3.Row, list[dict[str, str | None]]]] = []
        for feed in self.connection.execute(
            "SELECT name, url, ticker FROM feeds WHERE enabled = 1 ORDER BY name"
        ):
            request = urllib.request.Request(
                feed["url"], headers={"User-Agent": self.user_agent or "IntelligentInvestor/0.1"}
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                fetched.append((feed, list(parse_feed(response.read()))))

        inserted = 0
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        with revision_transaction(self.connection) as revision:
            for feed, items in fetched:
                for item in items:
                    external_id = hashlib.sha256(
                        str(item["external_id"]).encode("utf-8")
                    ).hexdigest()
                    cursor = self.connection.execute(
                        """INSERT INTO source_items(
                               source_name, external_id, ticker, title, published_at,
                               url, summary, fetched_at
                           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(source_name, external_id) DO UPDATE SET
                               title=excluded.title, published_at=excluded.published_at,
                               url=excluded.url, summary=excluded.summary,
                               fetched_at=excluded.fetched_at""",
                        (
                            feed["name"],
                            external_id,
                            feed["ticker"],
                            item["title"],
                            item["published_at"],
                            item["url"],
                            item["summary"],
                            now,
                        ),
                    )
                    inserted += cursor.rowcount
        return revision, inserted
