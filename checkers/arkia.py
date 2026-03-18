"""
Arkia (IZ) flight checker.

GitHub Actions IPs are blocked (403) by Arkia's WAF when using Playwright.
We first try a plain requests session (different TLS fingerprint — bypasses
JA3/JA4 bot detection) and scrape any JSON embedded in the HTML.
If that also returns 403, we fall back to Playwright.

If still no results: open DevTools > Network > XHR on arkia.co.il and
look for the availability API call; update INTERCEPT_PATTERNS accordingly.
"""
import logging
import re
import json
import requests
from .base import with_browser, search_with_interception, run_concurrent
from config import ROUTES

logger = logging.getLogger(__name__)

INTERCEPT_PATTERNS = [
    "availability",
    "flights",
    "search",
    "results",
    "offers",
    "fares",
    "/api/",
]

BOOKING_URL = "https://www.arkia.co.il/he/flights-results"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
}


async def check_arkia(origins: list, dates: list, adults: int, infants: int, control_checks: list = []) -> list:
    return await with_browser(_run, origins, dates, adults, infants, control_checks)


async def _run(context, origins, dates, adults, infants, control_checks):
    tasks = []
    for origin in origins:
        dests = ROUTES["arkia"].get(origin, [])
        for dest in dests:
            for date in dates:
                tasks.append(_search_one(context, origin, dest, date, adults, infants))
    for origin, dest, date in control_checks:
        tasks.append(_search_one(context, origin, dest, date, adults, infants))

    results = await run_concurrent(tasks)
    flights = []
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"Arkia search error: {r}")
        elif r:
            flights.extend(r)
    return flights


async def _search_one(context, origin, dest, date, adults, infants):
    date_fmt = date.replace("-", "")  # 20260318
    url = (
        f"{BOOKING_URL}?"
        f"CC=FL&IS_BACK_N_FORTH=false"
        f"&OB_DEP_CITY={origin}&OB_ARV_CITY={dest}"
        f"&OB_DATE={date_fmt}"
        f"&ADULTS={adults}&INFANTS={infants}"
    )

    logger.info(f"Arkia: {origin}→{dest} {date}")

    # --- Phase 1: plain HTTP request (different TLS fingerprint from Playwright) ---
    try:
        session = requests.Session()
        # Homepage first to pick up cookies / satisfy WAF session requirements
        session.get("https://www.arkia.co.il/", headers=_HEADERS, timeout=10)
        resp = session.get(
            url,
            headers={**_HEADERS, "Referer": "https://www.arkia.co.il/"},
            timeout=15,
        )
        logger.debug(f"Arkia HTTP: {resp.status_code} ({len(resp.content)} bytes)")
        logger.debug(f"Arkia HTML head: {resp.text[:400]}")
        if resp.status_code == 200 and resp.content:
            found = _parse_html(resp.text, origin, dest, date)
            if found:
                logger.info(f"Arkia HTTP: ✓ Found {len(found)} flight(s) {origin}→{dest} {date}")
                return found
    except Exception as e:
        logger.warning(f"Arkia HTTP error: {e}")

    # --- Phase 2: Playwright browser fallback ---
    captured = await search_with_interception(context, url, INTERCEPT_PATTERNS)
    flights = []
    for item in captured:
        parsed = _parse(item["data"], origin, dest, date)
        flights.extend(parsed)
        if parsed:
            logger.info(f"Arkia: ✓ Found {len(parsed)} flight(s) {origin}→{dest} {date}")
    return flights


def _parse_html(html: str, origin: str, dest: str, date: str) -> list:
    """Look for flight JSON embedded server-side in the page HTML."""
    book_url = (
        f"https://www.arkia.co.il/he/flights-results?"
        f"CC=FL&IS_BACK_N_FORTH=false"
        f"&OB_DEP_CITY={origin}&OB_ARV_CITY={dest}"
        f"&OB_DATE={date.replace('-','')}"
        f"&ADULTS=2&INFANTS=1"
    )
    for pattern in [
        r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});',
        r'window\.__DATA__\s*=\s*(\{.*?\});',
        r'window\.__PRELOADED_STATE__\s*=\s*(\{.*?\});',
        r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>',
    ]:
        m = re.search(pattern, html, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                logger.info(f"Arkia HTML: found embedded JSON")
                parsed = _parse(data, origin, dest, date)
                if parsed:
                    return parsed
            except Exception:
                pass
    return []


def _parse(data: dict | list, origin: str, dest: str, date: str) -> list:
    flights = []
    book_url = (
        f"https://www.arkia.co.il/he/flights-results?"
        f"CC=FL&IS_BACK_N_FORTH=false"
        f"&OB_DEP_CITY={origin}&OB_ARV_CITY={dest}"
        f"&OB_DATE={date.replace('-','')}"
        f"&ADULTS=2&INFANTS=1"
    )

    items = data if isinstance(data, list) else [data]
    for item in items:
        if not isinstance(item, dict):
            continue

        price = (
            item.get("price") or item.get("totalFare") or item.get("fare")
            or item.get("lowestFare") or item.get("amount")
        )
        dep_time = (
            item.get("departureTime") or item.get("std") or item.get("departure")
            or item.get("depTime")
        )
        flight_no = item.get("flightNumber") or item.get("flightNo") or "IZ"

        for key in ("flights", "journeys", "itineraries", "results", "lowFares"):
            if key in item and isinstance(item[key], list):
                flights.extend(_parse(item[key], origin, dest, date))

        if price is not None or dep_time is not None:
            flights.append({
                "airline": "Arkia",
                "origin": origin,
                "destination": dest,
                "date": date,
                "departure_time": str(dep_time) if dep_time else "See website",
                "price": str(price) if price else "See website",
                "flight_number": str(flight_no),
                "url": book_url,
            })

    return flights
