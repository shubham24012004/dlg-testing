"""Backwards-compatible CLI entry point for the refactored crawler."""

from General.Controllers.DlgCrawlerController import DlgCrawlerController


def main() -> None:
    controller = DlgCrawlerController()
    controller.run_scrape(
        master_csv="data\\lsp_sources_latest.csv",
        raw_csv="data\\dlg_raw_latest_v39.csv",
        limit=None,
    )


if __name__ == "__main__":
    main()