from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd

from DatabaseOperation.SQLAlchemy.DatabaseModels import LspMaster
from utils import parse_bool


class LspMasterManager:
    """Loads and filters ``lsp_master`` rows from CSV sources."""

    def load_active(self, csv_path: str | Path) -> List[LspMaster]:
        df = pd.read_csv(csv_path, dtype=str).fillna("")
        masters: List[LspMaster] = []
        for _, row in df.iterrows():
            lsp_name = row.get("lsp_name", "").strip()
            url = row.get("disclosure_url", "").strip()
            if not lsp_name or not url:
                continue
            masters.append(
                LspMaster(
                    lsp_name=lsp_name,
                    disclosure_url=url,
                    is_active=parse_bool(row.get("is_active", "true")),
                    fetch_hint=(row.get("fetch_hint", "auto").strip() or "auto"),
                    parse_hint=(row.get("parse_hint", "auto").strip() or "auto"),
                    rules_json=(row.get("rules_json", "").strip() or None),
                    lsp_id=(row.get("lsp_id", "").strip() or lsp_name),
                    home_url=(row.get("home_url", "").strip() or None),
                )
            )
        return [row for row in masters if row.is_active]
