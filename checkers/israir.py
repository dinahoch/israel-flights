"""
Israir (IS) flight checker.

Israir is a smaller carrier — they may use Hitit (Crane), Navitaire,
or a custom system. The booking engine is likely at israirairlines.com
or a booking subdomain.

If no results: check DevTools > Network > XHR on israirairlines.com
and update INTERCEPT_PATTERNS + BOOKING_URL accordingly.
"""
import logging
from .base import with_browser, search_with_interception, run_concurrent
from config import ROUTES

logger = logging.getLogger(__name__)

INTERCEPT_PATTERNS = [
    "availability",
    "search",
    "flights",
    "results",
    "offers",
    "/api/",
]

BOOKING_URL = "https://www.israir.co.il/he-IL/reservation/search/flights-abroad/results"


async def check_israir(origins: list, dates: list, adults: int, infants: int, control_checks: list = []) -> list:
    return await with_browser(_run, origins, dates, adults, infants, control_checks)


async def _run(context, origins, dates, adults, infants, control_checks):
    tasks = []
    for origin in origins:
        dests = ROUTES["israir"].get(origin, [])
        for dest in dests:
            for date in dates:
                tasks.append(_search_one(context, origin, dest, date, adults, infants))
    for origin, dest, date in control_checks:
        tasks.append(_search_one(context, origin, dest, date, adults, infants))

    results = await run_concurrent(tasks)
    flights = []
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"Israir search error: {r}")
        elif r:
            flights.extend(r)
    return flights


async def _search_one(context, origin, dest, date, adults, infants):
    import json, urllib.parse
    # Israir uses JSON-encoded city objects; TLV ltravelId is 2135
    # destination=undefined searches all destinations (we filter results to Europe)
    origin_obj = json.dumps({"type": "ltravelId", "destinationType": "CITY",
                             "cityCode": origin, "ltravelId": 2135,
                             "countryCode": None, "countryId": None})
    date_fmt = f"{date[8:10]}/{date[5:7]}/{date[:4]}"  # DD/MM/YYYY
    url = (
        f"{BOOKING_URL}?"
        f"origin={urllib.parse.quote(origin_obj)}"
        f"&destination=undefined"
        f"&startDate={date_fmt}"
        f"&adults={adults}&infants={infants}"
        f"&subject=ALL"
        f"&searchTime={date}T12:00:00.000Z"
    )

    logger.info(f"Israir: {origin}→{dest} {date}")
    captured = await search_with_interception(context, url, INTERCEPT_PATTERNS)

    flights = []
    for item in captured:
        parsed = _parse(item["data"], origin, dest, date)
        flights.extend(parsed)
        if parsed:
            logger.info(f"Israir: ✓ Found {len(parsed)} flight(s) {origin}→{dest} {date}")
    return flights


def _parse(data: dict | list, origin: str, dest: str, date: str) -> list:
    flights = []
    book_url = f"https://www.israirairlines.com/booking?from={origin}&to={dest}&date={date}&adults=2&infants=1&tripType=OW"

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
        )
        flight_no = item.get("flightNumber") or item.get("flightNo") or "IS"

        for key in ("flights", "journeys", "itineraries", "results"):
            if key in item and isinstance(item[key], list):
                flights.extend(_parse(item[key], origin, dest, date))

        if price is not None or dep_time is not None:
            flights.append({
                "airline": "Israir",
                "origin": origin,
                "destination": dest,
                "date": date,
                "departure_time": str(dep_time) if dep_time else "See website",
                "price": str(price) if price else "See website",
                "flight_number": str(flight_no),
                "url": book_url,
            })

    return flights
