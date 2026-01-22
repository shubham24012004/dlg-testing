"""Scraping Controller for scheduled DLG scraping operations."""
from __future__ import annotations

import logging
from typing import List

from General.Controllers.ApiController import ApiController
from General.Controllers.DlgCrawlerController import DlgCrawlerController

logger = logging.getLogger(__name__)


class ScrapingController:
    """Controller for scheduled scraping operations."""

    def __init__(self):
        """Initialize controllers."""
        self.api = ApiController()
        self.crawler = DlgCrawlerController()

    def run_cron_scrape(self) -> None:
        """Execute scheduled scraping for all active LSPs.
        
        This is called by APScheduler cron job.
        Fetches active sources and executes crawling for each.
        """
        logger.info("Starting cron scrape job")
        
        try:
            # Get active sources with joined config data
            sources = self.api.get_active_sources_for_scraping()
            
            if not sources:
                logger.warning("No active sources found for scraping")
                return
            
            logger.info("Found %d active sources to scrape", len(sources))
            
            # Use existing crawler controller method to process all sources
            self.crawler.run_scrape_sources(sources)
            
            logger.info("Cron scrape job completed")
            
        except Exception as e:
            logger.error("Cron scrape job failed: %s", str(e), exc_info=True)


__all__ = ["ScrapingController"]
