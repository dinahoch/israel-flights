"""
Air Haifa flight checker.

Air Haifa is a small domestic Israeli carrier (Haifa ↔ Eilat / domestic routes).
They are very unlikely to operate European routes. This checker is included for
completeness and will log what it finds on their site.

If Air Haifa does start operating European routes, update config.py ROUTES and
the INTERCEPT_PATTERNS / BOOKING_URL below.
"""
import logging
from .base import with_browser, search_with_interception
from config import ROUTES

logger = logging.getLogger(__name__)

INTERCEPT_PATTERNS = [
    "availability",
    "search",
    "flights",
    "booking",
]

BOOKING_URL = "https://www.airhaifa.co.il"


async def check_airhaifa(origins: list, dates: list, adults: int, infants: int) -> list:
    # Check if there are any routes configured; skip entirely if empty
    all_dests = [d for o in origins for d in ROUTES["airhaifa"].get(o, [])]
    if not all_dests:
        logger.info("Air Haifa: no European routes configured, skipping")
        return []

    return await with_browser(_run, origins, dates, adults, infants)


async def _run(context, origins, dates, adults, infants):
    flights = []
    for origin in origins:
        dests = ROUTES["airhaifa"].get(origin, [])
        for dest in dests:
            for date in dates:
                url = (
                    f"{BOOKING_URL}/booking?"
                    f"from={origin}&to={dest}&date={date}"
                    f"&adults={adults}&infants={infants}&children=0"
                )
                logger.info(f"Air Haifa: {origin}→{dest} {date}")
                captured = await search_with_interception(context, url, INTERCEPT_PATTERNS)
                for item in captured:
                    parsed = _parse(item["data"], origin, dest, date)
                    flights.extend(parsed)
    return flights


def _parse(data: dict | list, origin: str, dest: str, date: str) -> list:
    flights = []
    items = data if isinstance(data, list) else [data]
    for item in items:
        if not isinstance(item, dict):
            continue
        price = item.get("price") or item.get("fare")
        dep_time = item.get("departureTime") or item.get("std")
        if price is not None or dep_time is not None:
            flights.append({
                "airline": "Air Haifa",
                "origin": origin,
                "destination": dest,
                "date": date,
                "departure_time": str(dep_time) if dep_time else "See website",
                "price": str(price) if price else "See website",
                "url": BOOKING_URL,
            })
    return flights
