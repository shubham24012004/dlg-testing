from __future__ import annotations

try:
    from prometheus_client import Counter, Histogram  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    Counter = Histogram = None  # type: ignore


SCRAPE_SUCCESS = Counter("dlg_scrape_success_total", "Successful scrapes", ["status"]) if Counter else None
SCRAPE_DURATION = Histogram("dlg_scrape_duration_seconds", "Scrape duration") if Histogram else None

def record_scrape(status: str, duration_seconds: float | None = None) -> None:
    if SCRAPE_SUCCESS:
        SCRAPE_SUCCESS.labels(status=status).inc()
    if SCRAPE_DURATION and duration_seconds is not None:
        SCRAPE_DURATION.observe(duration_seconds)
