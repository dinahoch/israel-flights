"""
El Al (LY) flight checker.

El Al uses a custom React booking engine. The search widget on their homepage
POSTs to an internal REST API. We navigate to a pre-filled search URL and
intercept the JSON availability response.

If this checker returns nothing for routes you expect to have flights, open
Chrome DevTools > Network > Filter: Fetch/XHR, do a search on elal.com,
and look for a request with "availability" or "search" in its URL.
Update INTERCEPT_PATTERNS below with the actual path fragment.
"""
import logging
from .base import with_browser, search_with_interception, run_concurrent
from config import ROUTES

logger = logging.getLogger(__name__)

# URL fragment(s) that identify El Al's flight search API call.
# IMPORTANT: verify against actual network traffic if no results appear.
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

BOOKING_URL = "https://www.elal.com/en/flight-search"


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
    # Build the URL with query params — El Al's SPA should trigger the search.
    # The exact param names may differ; adjust if you see wrong/no results.
    date_fmt = date.replace("-", "")  # e.g. 20260318
    url = (
        f"{BOOKING_URL}?"
        f"origin={origin}&destination={dest}"
        f"&outboundDate={date}"
        f"&tripType=ONE_WAY"
        f"&adults={adults}&children=0&infants={infants}"
        f"&cabin=ECONOMY"
    )

    logger.info(f"El Al: {origin}→{dest} {date}")

    # El Al's /en/flight-search URL pre-fills the form but doesn't auto-submit.
    # We navigate there, then click the search button to trigger the API call.
    captured = []
    page = await context.new_page()

    async def on_response(response):
        if any(p in response.url for p in INTERCEPT_PATTERNS):
            try:
                import json as _json
                data = await response.json()
                captured.append({"url": response.url, "data": data})
                logger.info(f"El Al intercepted: {response.url}")
                logger.info(f"El Al response snippet: {_json.dumps(data)[:600]}")
            except Exception:
                pass

    page.on("response", on_response)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)
        # Try to click the search/submit button
        for selector in [
            "button[type='submit']",
            "button:has-text('Search')",
            "button:has-text('חפש')",
            "[data-testid*='search']",
            "[class*='search-btn']",
            "[class*='SearchButton']",
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
    Structure depends on El Al's API — this is a best-effort parser.
    Update once you see the actual response shape in the logs.
    """
    flights = []
    book_url = (
        f"https://www.elal.com/en/booking?"
        f"origin={origin}&destination={dest}"
        f"&departDate={date.replace('-','')}&tripType=OW&adults=2&infants=1"
    )

    # Flatten into a list for uniform handling
    items = data if isinstance(data, list) else [data]

    for item in items:
        if not isinstance(item, dict):
            continue

        # Try common field names used by airline APIs
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
            or item.get("std")  # Scheduled Time of Departure
            or item.get("depTime")
        )
        flight_no = (
            item.get("flightNumber")
            or item.get("flightNo")
            or item.get("number")
            or "LY"
        )

        # Recurse into nested structures (e.g. {"flights": [...], "fares": [...]})
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
