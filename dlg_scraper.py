"""Backwards-compatible CLI entry point for the refactored crawler."""

from General.Controllers.DlgCrawlerController import DlgCrawlerController


def main() -> None:
    controller = DlgCrawlerController()
    controller.run_scrape(limit=None)


if __name__ == "__main__":
    main()