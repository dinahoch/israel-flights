"""
El Al (LY) flight checker.

El Al's WAF blocks direct navigation to /en/flight-search — it requires a proper
session established from the homepage first.  We:
  1. Navigate to the El Al homepage to get cookies / set Referer.
  2. Navigate to the pre-filled search URL (WAF now sees a valid Referer).
  3. Try to click the Search button so the SPA fires its availability API.
  4. Intercept the JSON response.

If this still returns nothing, open Chrome DevTools > Network > Filter: Fetch/XHR,
search on elal.com, and look for a URL containing "availability" or "search".
Update INTERCEPT_PATTERNS below with the actual path fragment.
"""
import logging
from .base import with_browser, run_concurrent
from config import ROUTES

logger = logging.getLogger(__name__)

INTERCEPT_PATTERNS = [
    "availability",
    "flight-search",
    "flightSearch",
    "search/flights",
    "search",
    "flights",
    "offers",
    "fares",
    "itineraries",
]

HOMEPAGE = "https://www.elal.com/en"
SEARCH_URL = "https://www.elal.com/en/flight-search"

# Responses from these domains/paths are noise — skip them
_SKIP = ("analytics", "google", "facebook", "cdn", ".css", ".woff", ".png", ".jpg", ".svg", ".ico")


async def check_elal(origins: list, dates: list, adults: int, infants: int, control_checks: list = []) -> list:
    return await with_browser(_run, origins, dates, adults, infants, control_checks)


async def _run(context, origins, dates, adults, infants, control_checks):
    tasks = []
    for origin in origins:
        dests = ROUTES["elal"].get(origin, [])
        for dest in dests:
            for date in dates:
                tasks.append(_search_one(context, origin, dest, date, adults, infants))
    for origin, dest, date in control_checks:
        tasks.append(_search_one(context, origin, dest, date, adults, infants))

    results = await run_concurrent(tasks)
    flights = []
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"El Al search error: {r}")
        elif r:
            flights.extend(r)
    return flights


async def _search_one(context, origin, dest, date, adults, infants):
    url = (
        f"{SEARCH_URL}?"
        f"origin={origin}&destination={dest}"
        f"&outboundDate={date}"
        f"&tripType=ONE_WAY"
        f"&adults={adults}&children=0&infants={infants}"
        f"&cabin=ECONOMY"
    )

    logger.info(f"El Al: {origin}→{dest} {date}")

    captured = []
    page = await context.new_page()

    async def on_response(response):
        if any(s in response.url for s in _SKIP):
            return
        logger.debug(f"[El Al] {response.status} {response.url[:140]}")
        if any(p in response.url for p in INTERCEPT_PATTERNS):
            try:
                import json as _json
                data = await response.json()
                captured.append({"url": response.url, "data": data})
                logger.info(f"El Al intercepted: {response.url}")
                logger.info(f"El Al snippet: {_json.dumps(data)[:600]}")
            except Exception:
                pass

    page.on("response", on_response)
    try:
        # Step 1: homepage — establishes cookies and sets a valid Referer
        await page.goto(HOMEPAGE, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        # Step 2: pre-filled search URL (WAF should now accept it)
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        # Step 3: click Search button to trigger the availability API call
        for selector in [
            "button[type='submit']",
            "button:has-text('Search')",
            "button:has-text('חפש')",
            "[data-testid*='search']",
            "[class*='search-btn']",
            "[class*='SearchButton'i]",
        ]:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=1000):
                    await btn.click()
                    logger.info(f"El Al: clicked search button ({selector})")
                    break
            except Exception:
                continue

        await page.wait_for_timeout(10000)
    except Exception as e:
        logger.warning(f"El Al page error {origin}→{dest} {date}: {e}")
    finally:
        page.remove_listener("response", on_response)
        await page.close()

    flights = []
    for item in captured:
        parsed = _parse(item["data"], origin, dest, date)
        flights.extend(parsed)
        if parsed:
            logger.info(f"El Al: ✓ Found {len(parsed)} flight(s) {origin}→{dest} {date}")
    return flights


def _parse(data: dict | list, origin: str, dest: str, date: str) -> list:
    """
    Extract flights from the JSON response.
    Structure depends on El Al's API — update once you see the actual response shape in the logs.
    """
    flights = []
    book_url = (
        f"https://www.elal.com/en/booking?"
        f"origin={origin}&destination={dest}"
        f"&departDate={date.replace('-','')}&tripType=OW&adults=2&infants=1"
    )

    items = data if isinstance(data, list) else [data]

    for item in items:
        if not isinstance(item, dict):
            continue

        price = (
            item.get("price")
            or item.get("totalPrice")
            or item.get("fare")
            or item.get("lowestPrice")
            or item.get("amount")
        )
        dep_time = (
            item.get("departureTime")
            or item.get("departure")
            or item.get("std")
            or item.get("depTime")
        )
        flight_no = (
            item.get("flightNumber")
            or item.get("flightNo")
            or item.get("number")
            or "LY"
        )

        for key in ("flights", "itineraries", "results", "options", "segments"):
            if key in item and isinstance(item[key], list):
                flights.extend(_parse(item[key], origin, dest, date))

        if price is not None or dep_time is not None:
            flights.append({
                "airline": "El Al",
                "origin": origin,
                "destination": dest,
                "date": date,
                "departure_time": str(dep_time) if dep_time else "See website",
                "price": str(price) if price else "See website",
                "flight_number": str(flight_no),
                "url": book_url,
            })

    return flights
