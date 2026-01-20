from __future__ import annotations

from DatabaseOperation.SQLAlchemy.DatabaseModels import DlgCrawlerConfig, LspMaster


class DlgCrawlerConfigManager:
    """Creates crawl configs from ``LspMaster`` rows."""

    def build(self, master: LspMaster) -> DlgCrawlerConfig:
        return DlgCrawlerConfig(
            fetch_hint=master.fetch_hint,
            parse_hint=master.parse_hint,
            rules_json=master.rules_json,
        )
