import re
import time
import io
from collections import deque
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup
import pdfplumber

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


# ---- Keywords and URL patterns learned from your sample disclosure URLs ----
# DLG-specific keywords (must be present in content)
DLG_CONTENT_RE = re.compile(
    r"(default\s+loss\s+guarantee|first\s+loss\s+default\s+guarantee|"
    r"guidelines?\s+on\s+default\s+loss\s+guarantee|"  # Added for "Guidelines on Default Loss Guarantee"
    r"disclosure\s+under.*?default\s+loss\s+guarantee|"  # Added for "Disclosure Under ... Default Loss Guarantee"
    r"\bDLG\b.*?(portfolio|lender|nbfc|partner|outstanding)|"
    r"\bFLDG\b.*?(portfolio|lender|nbfc|partner)|"
    r"(portfolio|lender|nbfc).*?\bDLG\b|"
    r"outstanding\s+aum.*?(lender|partner|portfolio)|"
    r"lending\s+partner.*?(portfolio|outstanding|aum)|"
    r"digital\s+lending.*?(guarantee|portfolio))",
    re.I,
)

# Looser DLG validation for high-scoring URLs
DLG_CONTENT_LOOSE_RE = re.compile(
    r"(\bDLG\b|\bFLDG\b|default\s+loss|first\s+loss|"
    r"guideline.*?default.*?loss|disclosure.*?default.*?loss|"  # More flexible matching
    r"lending\s+partner|outstanding.*?(aum|portfolio)|"
    r"portfolio.*?(lender|nbfc|partner)|"
    r"digital\s+lending|nbfc.*?(partner|lender))",
    re.I | re.DOTALL,  # Added DOTALL to match across newlines
)

# General disclosure keywords (for URLs and links)
DISCLOSURE_KEYWORDS_RE = re.compile(
    r"(default\s+loss|dlg\b|fldg\b|other\s*disclos|disclosur|declarati|policy\s*disclos|website\s*disclos|compliance)",
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
    "/dlg-declaration",
    "/dlg-declaration/",
    "/dlg_declaration",
    "/dlg_declaration/",
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


def _check_dlg_content(session: requests.Session, url: str, timeout: int = 15, use_loose: bool = False) -> bool:
    """
    Verify that the page actually contains DLG-specific content.
    Returns True if DLG keywords are found in the page content.
    use_loose: If True, uses looser regex for high-scoring candidates
    """
    regex_pattern = DLG_CONTENT_LOOSE_RE if use_loose else DLG_CONTENT_RE
    
    try:
        r = session.get(url, timeout=timeout, allow_redirects=True)
        if r.status_code >= 400:
            return False
        
        # Check content type
        ctype = (r.headers.get("Content-Type") or "").lower()
        
        # For PDFs, extract text and check for DLG content
        if "application/pdf" in ctype or url.lower().endswith(".pdf"):
            try:
                with pdfplumber.open(io.BytesIO(r.content)) as pdf:
                    text = ""
                    # Check first few pages only (performance)
                    for page in pdf.pages[:5]:
                        page_text = page.extract_text() or ""
                        text += page_text + " "
                        # Early exit if we find DLG content
                        if regex_pattern.search(text):
                            return True
                    # Final check on all extracted text
                    return bool(regex_pattern.search(text))
            except Exception:
                return False
        
        # For HTML, check content
        if "text/html" in ctype or "application/xhtml" in ctype:
            html = r.text or ""
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(" ", strip=True)
            return bool(regex_pattern.search(text))
        
        return False
    except requests.RequestException:
        return False


def _score_candidate(url: str, anchor_text: str = "") -> float:
    u = (url or "").lower()
    t = (anchor_text or "").lower()
    score = 0.0

    # MAXIMUM priority: DLG in anchor text (like "DLG Declaration")
    if "dlg" in t or "fldg" in t:
        score += 20
    
    # Strong URL patterns (DLG-specific)
    if "dlg" in u or "fldg" in u:
        score += 15  # Highest priority for DLG-specific URLs
    
    if STRONG_URL_HINTS_RE.search(u):
        score += 10

    # Keyword in URL and/or text
    if DISCLOSURE_KEYWORDS_RE.search(u):
        score += 5
    if DISCLOSURE_KEYWORDS_RE.search(t):
        score += 5

    # Boost for PDFs (often contain disclosure data)
    if u.endswith(".pdf") or ".pdf?" in u:
        score += 3

    # Penalize non-DLG pages more heavily
    if any(x in u for x in ("/blog", "/careers", "/jobs", "/press", "/news", "/privacy", "/terms", "/cookie")):
        score -= 5
    
    # Penalize generic compliance/legal pages unless they have DLG keywords
    if any(x in u for x in ("/legal", "/policies", "/disclaimer", "/compliance")) and "dlg" not in u and "dlg" not in t:
        score -= 3

    return score


# ==================== FALLBACK STRATEGIES ====================

def _search_pdfs(session: requests.Session, homepage_url: str, origin: str) -> tuple[str | None, str]:
    """
    Strategy: Search specifically for PDF files that might contain DLG disclosures
    """
    try:
        html, _, _ = _fetch_html(session, homepage_url)
        if not html:
            return None, ""
        
        soup = BeautifulSoup(html, "html.parser")
        pdf_links = []
        
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if ".pdf" in href.lower():
                abs_url = urljoin(homepage_url, href)
                text = a.get_text(" ", strip=True)
                score = _score_candidate(abs_url, text)
                if score >= 10:  # Only consider relevant PDFs
                    pdf_links.append((abs_url, score))
        
        # Check best PDF
        if pdf_links:
            pdf_links.sort(key=lambda x: x[1], reverse=True)
            best_pdf = pdf_links[0][0]
            if _check_dlg_content(session, best_pdf, use_loose=True):
                return best_pdf, f"Fallback: PDF search (score: {pdf_links[0][1]:.1f})"
    except Exception:
        pass
    
    return None, ""


def _search_sitemap(session: requests.Session, origin: str) -> tuple[str | None, str]:
    """
    Strategy: Check sitemap.xml for disclosure URLs
    """
    sitemap_urls = [
        f"{origin}/sitemap.xml",
        f"{origin}/sitemap_index.xml",
        f"{origin}/sitemap-index.xml"
    ]
    
    try:
        for sitemap_url in sitemap_urls:
            try:
                r = session.get(sitemap_url, timeout=10)
                if r.status_code != 200:
                    continue
                
                # Parse XML
                root = ET.fromstring(r.content)
                # Handle namespaces
                ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
                
                urls = root.findall('.//ns:loc', ns) or root.findall('.//loc')
                
                for loc in urls:
                    url = loc.text
                    if url and any(keyword in url.lower() for keyword in ['dlg', 'disclosure', 'compliance', 'rbi']):
                        if _check_dlg_content(session, url, use_loose=True):
                            return url, "Fallback: Found in sitemap.xml"
            except Exception:
                continue
    except Exception:
        pass
    
    return None, ""


def _search_special_sections(session: requests.Session, homepage_url: str, origin: str) -> tuple[str | None, str]:
    """
    Strategy: Look for investor relations, regulatory, or compliance sections
    """
    special_paths = [
        "/investor-relations",
        "/investors",
        "/regulatory",
        "/regulatory-disclosures",
        "/rbi-compliance",
        "/compliance",
        "/legal-and-regulatory",
        "/about/compliance",
        "/company/compliance"
    ]
    
    for path in special_paths:
        try:
            url = urljoin(origin + "/", path.lstrip("/"))
            r = session.get(url, timeout=10, allow_redirects=True)
            if r.status_code >= 400:
                continue
            
            # Parse the section page
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                text = a.get_text(" ", strip=True)
                
                if any(kw in href.lower() or kw in text.lower() for kw in ['dlg', 'default loss', 'portfolio']):
                    abs_url = urljoin(r.url, href)
                    if _check_dlg_content(session, abs_url, use_loose=True):
                        return abs_url, f"Fallback: Found in {path}"
        except Exception:
            continue
    
    return None, ""


def find_dlg_disclosure_url(
    homepage_url: str,
    *,
    max_pages: int = 40,
    timeout: int = 20,
    delay_s: float = 0.05,
) -> tuple[str | None, str]:
    """
    Returns (url, reason) tuple where:
    - url: best-matching DLG/Disclosure link (page or PDF) or None
    - reason: explanation of result (why found or not found)

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
            # If it exists AND looks relevant, check content before returning
            if _score_candidate(cand) >= 10 and _check_dlg_content(session, cand):
                return cand, f"Found via fast-path probe: {path}"

    best_url = None
    best_score = float("-inf")
    crawled_pages = 0
    total_links_found = 0
    footer_links_found = 0
    pdfs_found = 0
    high_score_candidates = []  # Track candidates with score > 5
    homepage_accessible = True

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
        crawled_pages += 1
        if delay_s:
            time.sleep(delay_s)

        if not html:
            if page_url == homepage_url:
                homepage_accessible = False
            # Retry homepage with Playwright if initial fetch failed or returned empty
            if page_url == homepage_url and PLAYWRIGHT_AVAILABLE:
                try:
                    from playwright.sync_api import sync_playwright
                    with sync_playwright() as p:
                        browser = p.chromium.launch(headless=True)
                        page = browser.new_page()
                        page.goto(page_url, wait_until="networkidle", timeout=30000)
                        html = page.content().encode("utf-8", errors="ignore")
                        browser.close()
                        if html:
                            soup = BeautifulSoup(html, "html.parser")
                except Exception:
                    continue
            else:
                continue
        else:
            soup = BeautifulSoup(html, "html.parser")

        # Check if page has no links (JS-rendered) - try Playwright for homepage only
        all_links = soup.find_all("a", href=True)
        if page_url == homepage_url and len(all_links) == 0 and PLAYWRIGHT_AVAILABLE:
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.goto(page_url, wait_until="networkidle", timeout=30000)
                    html = page.content()
                    browser.close()
                    soup = BeautifulSoup(html, "html.parser")
            except Exception:
                pass

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
        
        footer_links_found += len(footer_links)

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
            if _is_asset(abs_u):
                continue
            
            txt = a.get_text(" ", strip=True) or ""
            
            # Allow external links if they're PDFs with high relevance scores
            is_external = not _same_site(origin, abs_u)
            is_pdf = abs_u.lower().endswith(".pdf") or ".pdf?" in abs_u.lower()
            score = _score_candidate(abs_u, txt)
            
            if is_pdf:
                pdfs_found += 1
            
            if is_external and not (is_pdf and score >= 15):
                # Skip external links unless they're highly-scored PDFs
                continue

            # score any disclosure-ish anchors
            if DISCLOSURE_KEYWORDS_RE.search(href) or DISCLOSURE_KEYWORDS_RE.search(txt) or STRONG_URL_HINTS_RE.search(abs_u):
                consider(abs_u, txt)
                total_links_found += 1
                
                # Track high-scoring candidates for diagnostics
                if score > 5 and len(high_score_candidates) < 5:
                    high_score_candidates.append((abs_u, score, txt[:50]))
                
                if not is_external:  # Only crawl same-site links
                    outlinks.append(abs_u)

        # If we found a very strong match, stop
        if best_url and best_score >= 14:
            # Use loose validation for very high scores (>20)
            use_loose = best_score >= 20
            if _check_dlg_content(session, best_url, use_loose=use_loose):
                return best_url, f"Found high-scoring link (score: {best_score:.1f})"

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

    # Final: validate best candidate has DLG content before returning
    if best_url and best_score > 0:
        # For high-scoring URLs, use looser validation
        session_final = requests.Session()
        session_final.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        
        # Use loose validation for scores >= 20, strict for lower scores
        use_loose = best_score >= 20
        
        if _check_dlg_content(session_final, best_url, use_loose=use_loose):
            validation_type = "loose" if use_loose else "strict"
            return best_url, f"Found after crawling {crawled_pages} pages (score: {best_score:.1f}, links evaluated: {total_links_found}, validation: {validation_type})"
        else:
            # Don't give up yet - try fallback strategies
            pass
    
    # ==================== FALLBACK STRATEGIES ====================
    # Primary search failed - try alternative approaches
    
    session_fallback = requests.Session()
    session_fallback.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    
    fallback_attempts = []
    
    # Strategy 1: Search for PDFs specifically
    pdf_url, pdf_reason = _search_pdfs(session_fallback, homepage_url, origin)
    if pdf_url:
        return pdf_url, pdf_reason
    else:
        fallback_attempts.append("PDF search: no DLG content in PDFs")
    
    # Strategy 2: Check sitemap.xml
    sitemap_url, sitemap_reason = _search_sitemap(session_fallback, origin)
    if sitemap_url:
        return sitemap_url, sitemap_reason
    else:
        fallback_attempts.append("sitemap.xml: not found or no relevant URLs")
    
    # Strategy 3: Check special sections (investor relations, regulatory, etc.)
    special_url, special_reason = _search_special_sections(session_fallback, homepage_url, origin)
    if special_url:
        return special_url, special_reason
    else:
        fallback_attempts.append("special sections: none found")
    
    # Build detailed failure message
    fallback_summary = "; ".join(fallback_attempts)
    
    # All strategies failed - provide comprehensive diagnostic message
    details = []
    
    if not homepage_accessible:
        details.append("⚠ Homepage inaccessible or returned empty content")
    
    details.append(f"Crawled {crawled_pages} pages")
    
    if footer_links_found > 0:
        details.append(f"analyzed {footer_links_found} footer links")
    else:
        details.append("no footer section found")
    
    if pdfs_found > 0:
        details.append(f"found {pdfs_found} PDFs")
    
    if total_links_found > 0:
        details.append(f"evaluated {total_links_found} disclosure-related links")
        if best_url and best_score > 0:
            details.append(f"best candidate score: {best_score:.1f} at {best_url[:60]}... (failed DLG content validation)")
        if high_score_candidates:
            candidate_list = "; ".join([f"{url[:40]}... (score: {sc:.1f})" for url, sc, txt in high_score_candidates[:3]])
            details.append(f"top candidates: {candidate_list}")
    else:
        details.append("no disclosure-related links found (site may use JavaScript navigation or non-standard structure)")
    
    details.append(f"Fallback attempts: {fallback_summary}")
    
    reason = "Not found - " + "; ".join(details)
    
    return None, reason
