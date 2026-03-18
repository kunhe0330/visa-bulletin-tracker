import re
import time
import logging
from datetime import datetime
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


def _fetch(url: str) -> str:
    """Fetch URL with retries."""
    headers = {"User-Agent": config.USER_AGENT}
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            logger.warning(f"Attempt {attempt}/{config.MAX_RETRIES} failed for {url}: {e}")
            if attempt < config.MAX_RETRIES:
                time.sleep(config.RETRY_DELAY * attempt)
            else:
                raise


def _normalize(text: str) -> str:
    """Normalize whitespace in text."""
    return re.sub(r"\s+", " ", text).strip()


def get_latest_bulletin_url() -> tuple[str, str]:
    """Find the latest bulletin URL from the index page.

    The page lists individual bulletin links like 'Visa Bulletin For April 2026'.
    We pick the first one that matches the pattern (newest bulletin).

    Returns (bulletin_url, bulletin_month_str) e.g.
    ('https://...', 'April 2026')
    """
    html = _fetch(config.BULLETIN_INDEX_URL)
    soup = BeautifulSoup(html, "html.parser")

    # Links are listed newest-first as "Visa Bulletin For {Month} {Year}"
    pattern = re.compile(r"visa bulletin for (\w+ \d{4})", re.IGNORECASE)
    for a_tag in soup.find_all("a", href=True):
        link_text = _normalize(a_tag.get_text())
        m = pattern.search(link_text)
        if m:
            href = a_tag["href"]
            url = urljoin(config.BASE_URL, href)
            month_str = m.group(1).title()  # e.g. "April 2026"
            return url, month_str

    raise RuntimeError("Could not find any bulletin link on the index page")


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
