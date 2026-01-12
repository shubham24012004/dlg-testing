import re
import time
from collections import deque
import pandas as pd
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


# ---- Keywords and URL patterns learned from your sample disclosure URLs ----
DISCLOSURE_KEYWORDS_RE = re.compile(
    r"(default\s+loss|dlg\b|fldg\b|other\s*disclos|disclosur|policy\s*disclos|website\s*disclos|compliance)",
    re.I,
)

# Strong URL hints (paths commonly used)
STRONG_URL_HINTS_RE = re.compile(
    r"(/dlg[-_/]?disclosure|/dlg[-_/]?portfolio|/other[-_/]?disclosures|/rbi[-_/]?disclosures|/policy[-_/]?disclosure|/website[-_/]?disclosure|/disclosures?)(/|$)",
    re.I,
)

# A practical list of common paths to probe FIRST (fast-path)
COMMON_DISCLOSURE_PATHS = [
    # your examples + common variants
    "/policy-disclosure",
    "/policy-disclosure/",
    "/dlg-disclosure",
    "/dlg-disclosure/",
    "/dlg_disclosure",
    "/dlg_disclosure/",
    "/dlg-portfolio",
    "/dlg-portfolio/",
    "/other-disclosures",
    "/other-disclosures/",
    "/legal/other-disclosures",
    "/legal/other-disclosures/",
    "/lending/other-disclosures",
    "/lending/other-disclosures/",
    "/disclosures",
    "/disclosures/",
    "/rbi-disclosures",
    "/rbi-disclosures/",
    "/website-disclosure",
    "/website-disclosure/",
    "/compliance",
    "/compliance/",
    "/compliance.html",
    "/disclosure",
    "/disclosure/",
    "/disclaimer",
    "/disclaimer/",
    "/legal",
    "/legal/",
    "/policies",
    "/policies/",
]

ASSET_EXT_RE = re.compile(r"\.(jpg|jpeg|png|gif|svg|webp|css|js|ico|zip|mp4)(\?|#|$)", re.I)


def _normalize_home(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise ValueError("homepage_url is empty")
    if not re.match(r"^https?://", url, flags=re.I):
        url = "https://" + url
    return url


def _origin(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _same_site(origin: str, candidate: str) -> bool:
    o = urlparse(origin)
    c = urlparse(candidate)
    return (not c.netloc) or (c.netloc.lower() == o.netloc.lower())


def _is_asset(url: str) -> bool:
    return bool(ASSET_EXT_RE.search(url))


def _is_bad_href(href: str) -> bool:
    h = (href or "").strip().lower()
    if not h:
        return True
    if h.startswith(("mailto:", "tel:", "javascript:", "whatsapp:", "intent:")):
        return True
    if h in ("#", "/#", "#/", "javascript:void(0)", "javascript:void(0);", "javascript:;"):
        return True
    return False


def _fetch_html(session: requests.Session, url: str, timeout: int = 20) -> tuple[str | None, str, int]:
    """
    Returns (html_or_none, final_url, status_code)
    """
    try:
        r = session.get(url, timeout=timeout, allow_redirects=True)
        status = r.status_code
        final_url = r.url
        if status >= 400:
            return None, final_url, status
        ctype = (r.headers.get("Content-Type") or "").lower()
        if "text/html" not in ctype and "application/xhtml" not in ctype:
            return None, final_url, status
        html = r.text or ""
        if len(html.strip()) < 200:
            return None, final_url, status
        return html, final_url, status
    except requests.RequestException:
        return None, url, 0


def _probe_url_exists(session: requests.Session, url: str, timeout: int = 15) -> bool:
    """
    Lightweight existence check using GET (HEAD is often blocked/misconfigured).
    """
    try:
        r = session.get(url, timeout=timeout, allow_redirects=True)
        if r.status_code >= 400:
            return False
        # Accept HTML or PDF or generic binary
        return True
    except requests.RequestException:
        return False


def _score_candidate(url: str, anchor_text: str = "") -> float:
    u = (url or "").lower()
    t = (anchor_text or "").lower()
    score = 0.0

    # Strong URL patterns
    if STRONG_URL_HINTS_RE.search(u):
        score += 10

    # Keyword in URL and/or text
    if DISCLOSURE_KEYWORDS_RE.search(u):
        score += 6
    if DISCLOSURE_KEYWORDS_RE.search(t):
        score += 6

    # Extra boosts
    if "dlg" in u or "fldg" in u:
        score += 4
    if u.endswith(".pdf") or ".pdf?" in u:
        score += 2

    # Penalize obvious non-targets
    if any(x in u for x in ("/blog", "/careers", "/jobs", "/press", "/news")):
        score -= 2

    return score


def find_dlg_disclosure_url(
    homepage_url: str,
    *,
    max_pages: int = 35,
    timeout: int = 20,
    delay_s: float = 0.05,
) -> str | None:
    """
    Returns the best-matching DLG/Disclosure link (page or PDF) for a website.

    Strategy:
      1) Fast-path: probe common disclosure URLs (including /policy-disclosure)
      2) Parse homepage & footer for disclosure-like links
      3) Shallow internal crawl (BFS) prioritizing disclosure-ish links
    """
    homepage_url = _normalize_home(homepage_url)
    origin = _origin(homepage_url)

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }
    )

    # 1) FAST-PATH: probe common paths
    for path in COMMON_DISCLOSURE_PATHS:
        cand = urljoin(origin + "/", path.lstrip("/"))
        if _probe_url_exists(session, cand):
            # If it exists AND looks relevant, return immediately
            if _score_candidate(cand) >= 10:
                return cand

    best_url = None
    best_score = float("-inf")

    def consider(url: str, anchor_text: str = ""):
        nonlocal best_url, best_score
        if not url or _is_asset(url):
            return
        sc = _score_candidate(url, anchor_text)
        if sc > best_score:
            best_score = sc
            best_url = url

    visited = set()
    q = deque([homepage_url])
    pages = 0

    while q and pages < max_pages:
        page_url = q.popleft()
        if page_url in visited:
            continue
        visited.add(page_url)

        if not _same_site(origin, page_url) or _is_asset(page_url):
            continue

        html, final_url, status = _fetch_html(session, page_url, timeout=timeout)
        pages += 1
        if delay_s:
            time.sleep(delay_s)

        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")

        # 2) Always prioritize footer links
        footer_nodes = soup.find_all("footer")
        if not footer_nodes:
            footer_nodes = soup.select('[id*="footer" i], [class*="footer" i]')

        footer_links = []
        for fn in footer_nodes:
            for a in fn.find_all("a", href=True):
                href = a.get("href", "")
                if _is_bad_href(href):
                    continue
                abs_u = urljoin(final_url, href)
                text = a.get_text(" ", strip=True) or ""
                footer_links.append((abs_u, text))

        # Evaluate footer links first
        for u, txt in footer_links:
            consider(u, txt)

        # 3) Evaluate relevant links across the page + enqueue
        outlinks = []
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if _is_bad_href(href):
                continue
            abs_u = urljoin(final_url, href)
            if _is_asset(abs_u) or not _same_site(origin, abs_u):
                continue
            txt = a.get_text(" ", strip=True) or ""

            # score any disclosure-ish anchors
            if DISCLOSURE_KEYWORDS_RE.search(href) or DISCLOSURE_KEYWORDS_RE.search(txt) or STRONG_URL_HINTS_RE.search(abs_u):
                consider(abs_u, txt)
                outlinks.append(abs_u)

        # If we found a very strong match, stop
        if best_url and best_score >= 14:
            return best_url

        # Enqueue strategy:
        # - footer links first (even if not keyworded, because disclosure pages are often there)
        # - then relevant links
        # - then a few generic internal links to avoid missing hidden pages
        enqueue = []

        for u, _txt in footer_links:
            if u not in visited:
                enqueue.append(u)

        for u in outlinks:
            if u not in visited:
                enqueue.append(u)

        # generic internal (bounded)
        generic = []
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if _is_bad_href(href):
                continue
            abs_u = urljoin(final_url, href)
            if _is_asset(abs_u) or not _same_site(origin, abs_u):
                continue
            generic.append(abs_u)
            if len(generic) >= 12:
                break

        enqueue.extend(generic)

        # de-dup enqueue
        seen = set()
        for u in enqueue:
            if u not in seen and u not in visited:
                q.append(u)
                seen.add(u)

    # Final: return best scoring candidate we saw
    return best_url if best_url and best_score > 0 else None


if __name__ == "__main__":
    source_url = "www.agrosperity.com"
    dlg_url = find_dlg_disclosure_url(source_url)
    print('Home URL: {0} - DLG URL: {1}'.format(source_url, dlg_url))

