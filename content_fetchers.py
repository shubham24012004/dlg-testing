import requests
from tenacity import retry, stop_after_attempt, wait_exponential
from DatabaseOperation.SQLAlchemy.DatabaseModels import FetchResult


BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

BROWSER_HEADERS = {
    "User-Agent": BROWSER_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}


# -----------------------------
# FETCH
# -----------------------------

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=12))
def fetch_with_requests(url: str, timeout: int = 40) -> FetchResult:
    r = requests.get(url, headers=BROWSER_HEADERS, timeout=timeout, allow_redirects=True)
    ct = r.headers.get("content-type", "") or ""
    return FetchResult(url=url, status_code=r.status_code, content_type=ct, body=r.content, fetch_mode_used="requests")
