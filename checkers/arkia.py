"""
Arkia (IZ) flight checker.

Arkia uses Navitaire NewSkies as their booking engine (confirmed).
Navitaire's REST API is typically at a booking subdomain and responds to
POST /api/v1/availability/search or GET /nsk/api/... calls.

If no results: open DevTools > Network > XHR while searching on arkia.com,
find the availability request, and update INTERCEPT_PATTERNS + BOOKING_URL.
Common Navitaire clues: paths contain /nsk/, /newskies/, or /api/v1/availability.
"""
import logging
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
    captured = await search_with_interception(context, url, INTERCEPT_PATTERNS)

    flights = []
    for item in captured:
        parsed = _parse(item["data"], origin, dest, date)
        flights.extend(parsed)
        if parsed:
            logger.info(f"Arkia: ✓ Found {len(parsed)} flight(s) {origin}→{dest} {date}")
    return flights


def _parse(data: dict | list, origin: str, dest: str, date: str) -> list:
    flights = []
    book_url = f"https://www.arkia.com/booking?from={origin}&to={dest}&date={date}&adult=2&infant=1&triptype=OW"

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
