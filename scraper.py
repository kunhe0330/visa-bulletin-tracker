import calendar
import re
import time
import logging
from datetime import date, datetime
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)

MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4,
    "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8,
    "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def parse_bulletin_date(date_str: str) -> Optional[datetime]:
    """Parse date like '01JUN24', '22APR23', 'C', 'U'."""
    s = date_str.strip().upper()
    if s == "C":
        return "C"
    if s == "U":
        return "U"
    # Match DDMMMYY
    m = re.match(r"^(\d{1,2})([A-Z]{3})(\d{2})$", s)
    if not m:
        raise ValueError(f"Cannot parse bulletin date: '{date_str}'")
    day = int(m.group(1))
    month = MONTH_MAP.get(m.group(2))
    if month is None:
        raise ValueError(f"Unknown month abbreviation: '{m.group(2)}'")
    year = int(m.group(3))
    year += 2000 if year < 80 else 1900
    return datetime(year, month, day).date()


# travel.state.gov sits behind aggressive bot protection (Akamai redirect
# loops, then Cloudflare 403s) that fingerprints the TLS handshake itself, so
# plain python-requests gets blocked regardless of headers. Fetch strategy:
#   1. curl_cffi impersonating a real Chrome TLS fingerprint (if installed)
#   2. plain requests with browser-like headers (works when protection is lax)
#   3. Wayback Machine snapshot — bulletins are static once published, so a
#      slightly stale archive copy is an acceptable last resort
BROWSER_HEADERS = {
    "User-Agent": config.USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

_session: Optional[requests.Session] = None
_curl_session = None


def _new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)
    # Fail fast instead of chasing a redirect loop 30 times per attempt
    session.max_redirects = 10
    return session


def _fetch_via_browser_tls(url: str) -> str:
    """Fetch with curl_cffi impersonating Chrome's TLS fingerprint."""
    global _curl_session
    if curl_requests is None:
        raise RuntimeError("curl_cffi not installed")
    try:
        if _curl_session is None:
            _curl_session = curl_requests.Session(impersonate="chrome")
        resp = _curl_session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.text
    except Exception:
        _curl_session = None  # cookie state may be poisoned, start clean next time
        raise


def _fetch_via_requests(url: str) -> str:
    """Fetch with plain requests, keeping cookies across requests."""
    global _session
    try:
        if _session is None:
            _session = _new_session()
        resp = _session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.text
    except Exception:
        _session = None
        raise


def _raw_get(url: str, timeout: int = 45) -> tuple[str, str]:
    """Single GET preferring curl_cffi's browser TLS. Returns (text, final_url).

    archive.org also 403s datacenter IPs with non-browser clients at times,
    so archive requests get the same browser treatment as the main site.
    """
    if curl_requests is not None:
        try:
            resp = curl_requests.get(url, impersonate="chrome", timeout=timeout)
            resp.raise_for_status()
            return resp.text, str(resp.url)
        except Exception as e:
            logger.debug(f"Browser-TLS GET failed for {url}, using requests: {e}")
    resp = requests.get(url, headers=BROWSER_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.text, resp.url


def _fetch_via_wayback(url: str) -> str:
    """Fetch the most recent Wayback Machine snapshot of the page.

    Requesting /web/<future-timestamp>id_/<url> redirects to the newest
    capture; the 'id_' flag returns the original HTML without archive.org's
    link rewriting. If the raw mode fails, fall back to the rewritten page —
    the bulletin tables survive rewriting and link parsing handles both forms.
    """
    last_error = None
    for mode in ("id_", ""):
        snap_url = f"https://web.archive.org/web/20991231{mode}/{url}"
        try:
            text, final_url = _raw_get(snap_url)
            logger.info(f"Using Wayback snapshot: {final_url}")
            return text
        except Exception as e:
            last_error = e
    raise last_error


_html_cache: dict[str, str] = {}


def _fetch(url: str) -> str:
    """Fetch URL, trying each strategy in order with retries."""
    if url in _html_cache:
        return _html_cache[url]

    strategies = [
        ("browser-tls", _fetch_via_browser_tls),
        ("requests", _fetch_via_requests),
        ("wayback", _fetch_via_wayback),
    ]
    if curl_requests is None:
        strategies.pop(0)

    # Hard per-URL time budget: archive.org can hang for minutes per request
    # when overloaded, and a cron run must never take tens of minutes.
    deadline = time.monotonic() + config.FETCH_BUDGET

    errors: dict[str, str] = {}
    for attempt in range(1, config.MAX_RETRIES + 1):
        for name, fetcher in strategies:
            if time.monotonic() > deadline:
                logger.warning(f"Fetch budget ({config.FETCH_BUDGET}s) exhausted for {url}")
                break
            try:
                html = fetcher(url)
                if name != strategies[0][0] or attempt > 1:
                    logger.info(f"Fetched {url} via '{name}' on attempt {attempt}")
                _html_cache[url] = html
                return html
            except Exception as e:
                logger.warning(
                    f"[{name}] attempt {attempt}/{config.MAX_RETRIES} failed for {url}: {e}"
                )
                errors[name] = str(e).splitlines()[0][:120] if str(e) else type(e).__name__
        if time.monotonic() > deadline:
            break
        if attempt < config.MAX_RETRIES:
            time.sleep(config.RETRY_DELAY * attempt)

    summary = "; ".join(f"{name}: {msg}" for name, msg in errors.items())
    raise RuntimeError(f"모든 소스에서 가져오기 실패 ({url}) — {summary}")


def _normalize(text: str) -> str:
    """Normalize whitespace in text."""
    return re.sub(r"\s+", " ", text).strip()


def _build_bulletin_url(month: int, year: int) -> str:
    """Build a bulletin URL from its month. Pages live under their federal
    fiscal year (Oct-Sep), e.g. the October 2026 bulletin is under /2027/."""
    fiscal_year = year + 1 if month >= 10 else year
    month_name = calendar.month_name[month].lower()
    return (
        f"{config.BASE_URL}/content/travel/en/legal/visa-law0/visa-bulletin/"
        f"{fiscal_year}/visa-bulletin-for-{month_name}-{year}.html"
    )


def _candidate_bulletins(today: Optional[date] = None) -> list[tuple[int, int]]:
    """Newest-first (month, year) candidates for the latest bulletin.

    The bulletin for month M is published mid-month M-1, so at any given date
    the latest bulletin is either next month's or the current month's.
    """
    today = today or date.today()
    month, year = today.month, today.year
    next_month, next_year = (1, year + 1) if month == 12 else (month + 1, year)
    return [(next_month, next_year), (month, year)]


def get_latest_bulletin_url() -> tuple[str, str]:
    """Find the latest bulletin URL from the index page.

    The page lists individual bulletin links like 'Visa Bulletin For April 2026'.
    We pick the first one that matches the pattern (newest bulletin). If the
    index page is unreachable on every source, fall back to probing the
    deterministic bulletin URLs for next month and the current month directly.

    Returns (bulletin_url, bulletin_month_str) e.g.
    ('https://...', 'April 2026')
    """
    try:
        html = _fetch(config.BULLETIN_INDEX_URL)
        soup = BeautifulSoup(html, "html.parser")

        # Links are listed newest-first as "Visa Bulletin For {Month} {Year}"
        pattern = re.compile(r"visa bulletin for (\w+ \d{4})", re.IGNORECASE)
        for a_tag in soup.find_all("a", href=True):
            link_text = _normalize(a_tag.get_text())
            m = pattern.search(link_text)
            if m:
                href = a_tag["href"]
                # Wayback-rewritten pages embed the original URL in the href
                embedded = re.search(r"https?://travel\.state\.gov\S+", href)
                url = embedded.group(0) if embedded else urljoin(config.BASE_URL, href)
                month_str = m.group(1).title()  # e.g. "April 2026"
                return url, month_str

        raise RuntimeError("Could not find any bulletin link on the index page")
    except Exception as e:
        logger.warning(f"Index page unavailable ({e}); probing bulletin URLs directly")

    last_error = None
    for month, year in _candidate_bulletins():
        url = _build_bulletin_url(month, year)
        try:
            _fetch(url)  # result is cached for the scrape that follows
        except Exception as e:
            last_error = e
            continue
        month_str = f"{calendar.month_name[month]} {year}"
        logger.info(f"Found latest bulletin by direct URL probe: {month_str}")
        return url, month_str

    raise RuntimeError(
        f"인덱스 페이지와 직접 URL 추정 모두 실패. 마지막 오류: {last_error}"
    )


def _extract_month_from_url(url: str) -> Optional[str]:
    """Extract bulletin month from URL like '.../visa-bulletin-for-april-2026.html'."""
    m = re.search(r"visa-bulletin-for-(\w+)-(\d{4})", url.lower())
    if m:
        month_name = m.group(1).capitalize()
        year = m.group(2)
        return f"{month_name} {year}"
    return None


def _find_eb_tables(soup: BeautifulSoup) -> tuple:
    """Find the two Employment-Based tables (Final Action, Dates for Filing)."""
    eb_tables = []
    for table in soup.find_all("table"):
        first_cell = table.find("td")
        if first_cell:
            cell_text = _normalize(first_cell.get_text()).lower()
            if "employment" in cell_text and "based" in cell_text:
                eb_tables.append(table)

    if len(eb_tables) < 2:
        raise RuntimeError(
            f"Expected 2 Employment-Based tables, found {len(eb_tables)}"
        )

    return eb_tables[0], eb_tables[1]


def _parse_eb_table(table) -> dict:
    """Parse an EB table and extract EB-3 data.

    Returns dict with keys:
      'eb3_professionals': date or 'C' or 'U'
      'eb3_other_workers': date or 'C' or 'U'
    """
    rows = table.find_all("tr")
    # Column index for "All Chargeability Areas" is 1 (second column)
    all_charge_col = 1

    result = {}
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        label = _normalize(cells[0].get_text()).lower()

        if label == "3rd":
            date_text = _normalize(cells[all_charge_col].get_text())
            result["eb3_professionals"] = parse_bulletin_date(date_text)
        elif "other workers" in label:
            date_text = _normalize(cells[all_charge_col].get_text())
            result["eb3_other_workers"] = parse_bulletin_date(date_text)

    if "eb3_professionals" not in result:
        raise RuntimeError("Could not find EB-3 (3rd) row in table")
    if "eb3_other_workers" not in result:
        raise RuntimeError("Could not find Other Workers row in table")

    return result


def scrape_bulletin(url: Optional[str] = None) -> dict:
    """Scrape a Visa Bulletin page.

    If url is None, finds the latest bulletin from the index page.

    Returns dict:
    {
        'bulletin_month': 'April 2026',
        'bulletin_url': 'https://...',
        'final_action': {'eb3_professionals': date, 'eb3_other_workers': date},
        'dates_for_filing': {'eb3_professionals': date, 'eb3_other_workers': date},
    }
    """
    if url is None:
        url, month_str = get_latest_bulletin_url()
    else:
        month_str = _extract_month_from_url(url)

    logger.info(f"Scraping bulletin: {url}")
    html = _fetch(url)
    soup = BeautifulSoup(html, "html.parser")

    # Try to get month from page title if not from URL
    if not month_str:
        title = soup.find("title")
        if title:
            m = re.search(r"Visa Bulletin [Ff]or (\w+ \d{4})", title.get_text())
            if m:
                month_str = m.group(1)
        if not month_str:
            # Search in h1/h2
            for heading in soup.find_all(["h1", "h2", "h3"]):
                m = re.search(r"Visa Bulletin [Ff]or (\w+ \d{4})", heading.get_text())
                if m:
                    month_str = m.group(1)
                    break

    if not month_str:
        raise RuntimeError("Could not determine bulletin month")

    final_action_table, filing_table = _find_eb_tables(soup)

    return {
        "bulletin_month": month_str,
        "bulletin_url": url,
        "final_action": _parse_eb_table(final_action_table),
        "dates_for_filing": _parse_eb_table(filing_table),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = scrape_bulletin()
    print(f"Bulletin Month: {result['bulletin_month']}")
    print(f"URL: {result['bulletin_url']}")
    print(f"Final Action: {result['final_action']}")
    print(f"Dates for Filing: {result['dates_for_filing']}")
