from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession}/{document}"


@dataclass(frozen=True)
class Company:
    cik: str
    ticker: str
    name: str


class SecClient:
    def __init__(
        self,
        user_agent: str,
        min_interval: float = 0.12,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.min_interval = min_interval
        self._last_request = 0.0
        self._opener = opener or urllib.request.urlopen

    def _request(self, url: str) -> bytes:
        delay = self.min_interval - (time.monotonic() - self._last_request)
        if delay > 0:
            time.sleep(delay)
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept-Encoding": "identity",
                "Accept": "application/json,text/html,*/*",
            },
        )
        try:
            with self._opener(request, timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"SEC request failed ({exc.code}) for {url}") from exc
        finally:
            self._last_request = time.monotonic()

    def json(self, url: str) -> dict[str, Any]:
        return json.loads(self._request(url))

    def resolve_ticker(self, ticker: str) -> Company:
        wanted = ticker.upper()
        for entry in self.json(TICKERS_URL).values():
            if entry["ticker"].upper() == wanted:
                return Company(
                    cik=str(entry["cik_str"]).zfill(10),
                    ticker=wanted,
                    name=entry["title"],
                )
        raise ValueError(f"Ticker not found in SEC company list: {ticker}")

    def submissions(self, cik: str) -> dict[str, Any]:
        return self.json(SUBMISSIONS_URL.format(cik=cik))

    def company_facts(self, cik: str) -> dict[str, Any]:
        return self.json(COMPANY_FACTS_URL.format(cik=cik))

    def download_filing(
        self, cik: str, accession_number: str, primary_document: str, destination: Path
    ) -> str:
        accession = accession_number.replace("-", "")
        url = ARCHIVE_URL.format(
            cik_int=int(cik), accession=accession, document=primary_document
        )
        content = self._request(url)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(destination)
        return url
