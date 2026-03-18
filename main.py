"""
Main entry point for the Israel flight checker.
Runs all airline checkers, deduplicates results, and sends email notifications.
"""
import asyncio
import logging
import sys

from checkers.elal import check_elal
from checkers.arkia import check_arkia
from checkers.israir import check_israir
from checkers.airhaifa import check_airhaifa
from config import ORIGINS, DATES, ADULTS, INFANTS, CONTROL_CHECKS, ROUTES
from notify import send_notification
from state import filter_new, save_seen

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

CHECKERS = [
    ("El Al",     "elal",     check_elal),
    ("Arkia",     "arkia",    check_arkia),
    ("Israir",    "israir",   check_israir),
    ("Air Haifa", "airhaifa", check_airhaifa),
]


async def main():
    logger.info(f"Starting flight check — origins: {ORIGINS}, dates: {DATES}")

    all_flights = []
    for name, key, checker in CHECKERS:
        control = CONTROL_CHECKS[key]
        logger.info(f"Checking {name} (control: {control[0]}→{control[1]} {control[2]})...")
        try:
            # Phase 1: control check — one known route that should always have seats
            control_results = await checker([], [], ADULTS, INFANTS, [control])
            if not control_results:
                logger.warning(f"{name}: control check returned 0 results — scraper may be broken, skipping this airline")
                continue

            logger.info(f"{name}: control check passed ({len(control_results)} result(s))")

            # Phase 2: full search across all dates and destinations
            # TODO: uncomment once control checks pass for all airlines
            # flights = await checker(ORIGINS, DATES, ADULTS, INFANTS, [])
            # logger.info(f"{name}: {len(flights)} flight(s) found")
            # all_flights.extend(flights)
        except Exception as e:
            logger.error(f"{name} checker failed: {e}", exc_info=True)

    logger.info(f"Total flights found across all airlines: {len(all_flights)}")

    if not all_flights:
        logger.info("No flights found this run — no notification sent")
        return

    new_flights, updated_seen = filter_new(all_flights)

    if not new_flights:
        logger.info("All flights already notified — skipping email")
        return

    logger.info(f"Sending notification for {len(new_flights)} new flight(s)")
    send_notification(new_flights)
    save_seen(updated_seen)


if __name__ == "__main__":
    asyncio.run(main())
