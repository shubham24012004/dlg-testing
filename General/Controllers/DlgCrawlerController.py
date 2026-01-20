from __future__ import annotations

from typing import Optional

from General.Managers.DlgCrawlerManager import DlgCrawlerManager


class DlgCrawlerController:
    """User-facing entry point that wires inputs to the crawler manager."""

    def __init__(self, manager: Optional[DlgCrawlerManager] = None) -> None:
        self.manager = manager or DlgCrawlerManager()

    def run_scrape(self, master_csv: str, raw_csv: str, limit: Optional[int] = None) -> None:
        self.manager.run(master_csv, raw_csv, limit)
