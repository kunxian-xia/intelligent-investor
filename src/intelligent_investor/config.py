from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    user_agent: str

    @property
    def database_path(self) -> Path:
        return self.data_dir / "investor.sqlite3"

    @property
    def filing_dir(self) -> Path:
        return self.data_dir / "filings"

    @property
    def excel_path(self) -> Path:
        return self.data_dir / "financials.xlsx"


def load_settings() -> Settings:
    data_dir = Path(os.getenv("INVESTOR_DATA_DIR", "./data")).expanduser().resolve()
    user_agent = os.getenv("SEC_USER_AGENT", "").strip()
    return Settings(data_dir=data_dir, user_agent=user_agent)


def require_sec_identity(settings: Settings) -> None:
    if not settings.user_agent or "@" not in settings.user_agent:
        raise ValueError(
            "Set SEC_USER_AGENT to an application name and contact email, for example "
            "'IntelligentInvestor you@example.com'."
        )
