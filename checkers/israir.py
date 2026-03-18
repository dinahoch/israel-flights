"""
Israir (IS) flight checker.

Israir's booking engine at israir.co.il intercepts JSON from /api/search/FLIGHTS.
Using destination=undefined returns all destinations in one call, so we make
one page load per (origin, date) instead of one per (origin, dest, date).

If no results: check DevTools > Network > XHR on israir.co.il and update
INTERCEPT_PATTERNS + BOOKING_URL accordingly.
"""
import logging
from .base import with_browser, search_with_interception, run_concurrent
from config import ROUTES

logger = logging.getLogger(__name__)

INTERCEPT_PATTERNS = [
    "/api/search/FLIGHTS",
    "/api/engine",
]

BOOKING_URL = "https://www.israir.co.il/he-IL/reservation/search/flights-abroad/results"


async def check_israir(origins: list, dates: list, adults: int, infants: int, control_checks: list = []) -> list:
    return await with_browser(_run, origins, dates, adults, infants, control_checks)


async def _run(context, origins, dates, adults, infants, control_checks):
    tasks = []
    seen = set()

    # One page load per (origin, date) — destination=undefined returns all destinations
    for origin in origins:
        allowed = ROUTES["israir"].get(origin, [])
        if not allowed:
            continue
        for date in dates:
            key = (origin, date)
            if key not in seen:
                seen.add(key)
                tasks.append(_search_one(context, origin, allowed, date, adults, infants))

    # Control checks: filter to the specific control destination
    for origin, dest, date in control_checks:
        tasks.append(_search_one(context, origin, [dest], date, adults, infants))

    # Israir's React app detects concurrent page loads in the same browser
    # context (shared cookies/localStorage) and suppresses the search API call.
    # Run one page at a time to avoid this.
    results = await run_concurrent(tasks, concurrency=1)
    flights = []
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"Israir search error: {r}")
        elif r:
            flights.extend(r)
    return flights


async def _search_one(context, origin, allowed_dests, date, adults, infants):
    import json, urllib.parse
    # Israir uses JSON-encoded city objects; TLV ltravelId is 2135
    origin_obj = json.dumps({
        "type": "ltravelId", "destinationType": "CITY",
        "cityCode": origin, "ltravelId": 2135,
        "countryCode": None, "countryId": None,
    })
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

    logger.info(f"Israir: {origin}→[all] {date} (filtering to {allowed_dests})")
    captured = await search_with_interception(context, url, INTERCEPT_PATTERNS, timeout_ms=25000)

    flights = []
    for item in captured:
        if "/api/search/FLIGHTS" in item["url"]:
            parsed = _parse(item["data"], origin, date, allowed_dests)
            flights.extend(parsed)
            if parsed:
                dests_found = sorted({f["destination"] for f in parsed})
                logger.info(f"Israir: ✓ {len(parsed)} flight(s) {origin}→{dests_found} {date}")
    return flights


def _parse(data: dict, origin: str, date: str, allowed_dests: list) -> list:
    """
    Parse /api/search/FLIGHTS response.

    Structure:
      data.ltsPackages[]  (direct packages)
      data.additionalPackagesResponse.ltsPackages[]  (charter/additional)
        .legGroups[].legList[].legOptionList[]
          .legSegmentList[0].depLoc.scheduledDateTime  "DD/MM/YYYY HH:MM:SS"
          .legSegmentList[-1].arrLoc.location           IATA code
    """
    flights = []
    if not isinstance(data, dict):
        return flights

    top = data.get("data", {})
    packages = list(top.get("ltsPackages", []))
    additional = top.get("additionalPackagesResponse", {})
    if isinstance(additional, dict):
        packages.extend(additional.get("ltsPackages", []))

    # Log field names of the first package/option so we can identify the
    # exact availability field if our heuristic misses any sold-out flights.
    if packages and isinstance(packages[0], dict):
        logger.debug(f"Israir pkg keys: {list(packages[0].keys())}")
        _lg = packages[0].get("legGroups", [{}])
        _ll = _lg[0].get("legList", [{}]) if _lg else []
        _ol = _ll[0].get("legOptionList", [{}]) if _ll else []
        if _ol:
            logger.debug(f"Israir legOption keys: {list(_ol[0].keys())}")

    for pkg in packages:
        if not isinstance(pkg, dict):
            continue
        if _is_sold_out(pkg):
            continue
        pkg_price = _extract_price(pkg)

        for leg_group in pkg.get("legGroups", []):
            for leg in leg_group.get("legList", []):
                for option in leg.get("legOptionList", []):
                    if _is_sold_out(option):
                        continue
                    opt_price = _extract_price(option) or pkg_price
                    segments = option.get("legSegmentList", [])
                    if not segments:
                        continue

                    dep_loc = segments[0].get("depLoc", {})
                    arr_loc = segments[-1].get("arrLoc", {})

                    dest = arr_loc.get("location", "")
                    if dest not in allowed_dests:
                        continue

                    dep_raw = dep_loc.get("scheduledDateTime", "")
                    dep_time = dep_raw.split(" ")[1][:5] if " " in dep_raw else dep_raw

                    flight_no = (
                        segments[0].get("flightNumber")
                        or segments[0].get("flightNo")
                        or "6H"
                    )

                    import json as _json, urllib.parse as _up
                    _origin_obj = _json.dumps({
                        "type": "ltravelId", "destinationType": "CITY",
                        "cityCode": origin, "ltravelId": 2135,
                        "countryCode": None, "countryId": None,
                    })
                    _date_fmt = f"{date[8:10]}/{date[5:7]}/{date[:4]}"
                    book_url = (
                        f"https://www.israir.co.il/he-IL/reservation/search/flights-abroad/results?"
                        f"origin={_up.quote(_origin_obj)}"
                        f"&destination={dest}"
                        f"&startDate={_date_fmt}"
                        f"&adults=2&infants=1&subject=ALL"
                        f"&searchTime={date}T12:00:00.000Z"
                    )

                    flights.append({
                        "airline": "Israir",
                        "origin": origin,
                        "destination": dest,
                        "date": date,
                        "departure_time": dep_time,
                        "price": str(opt_price) if opt_price is not None else "See website",
                        "flight_number": str(flight_no),
                        "url": book_url,
                    })

    return flights


def _is_sold_out(obj: dict) -> bool:
    """Return True if this package/option is sold out or has no availability."""
    if not isinstance(obj, dict):
        return False
    # Boolean sold-out flags
    for key in ("isSoldOut", "soldOut", "isFullFlight", "isFull", "isClosed", "isUnavailable"):
        if obj.get(key) is True:
            return True
    # Inverse availability flags
    for key in ("isAvailable", "hasAvailability", "available"):
        v = obj.get(key)
        if v is False:
            return True
    # Numeric seat counts
    for key in ("seatsAvailable", "availableSeats", "seats", "availability"):
        v = obj.get(key)
        if isinstance(v, (int, float)) and v <= 0:
            return True
    # String status values
    _SOLD_OUT = {"SOLD_OUT", "FULL", "CLOSED", "NONE", "UNAVAILABLE", "NO_AVAILABILITY", "INACTIVE"}
    for key in ("status", "fareAvailability", "availabilityStatus", "flightStatus"):
        v = obj.get(key)
        if isinstance(v, str) and v.upper() in _SOLD_OUT:
            return True
    return False


def _extract_price(obj: dict):
    if not isinstance(obj, dict):
        return None
    for key in ("totalPrice", "price", "lowestPrice", "amount", "fare", "totalFare"):
        v = obj.get(key)
        if v is not None:
            return v
    price_list = obj.get("priceList", [])
    if isinstance(price_list, list) and price_list:
        return _extract_price(price_list[0])
    return None
