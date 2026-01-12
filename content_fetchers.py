import requests
from tenacity import retry, stop_after_attempt, wait_exponential
from models import FetchResult


# -----------------------------
# FETCH
# -----------------------------

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=12))
def fetch_with_requests(url: str, timeout: int = 40) -> FetchResult:
    headers = {"User-Agent": "DLG-Monitor/1.0 (+dl-monitoring; contact=ops@example.org)"}
    r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    ct = r.headers.get("content-type", "") or ""
    return FetchResult(url=url, status_code=r.status_code, content_type=ct, body=r.content, fetch_mode_used="requests")
