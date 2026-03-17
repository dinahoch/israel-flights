"""
Tracks which flights we've already notified about to avoid duplicate emails.
State is stored in state.json, which is committed back to the repo by the
GitHub Actions workflow after each run.
"""
import json
import os

STATE_FILE = os.path.join(os.path.dirname(__file__), "state.json")


def load_seen() -> set[str]:
    if not os.path.exists(STATE_FILE):
        return set()
    with open(STATE_FILE) as f:
        return set(json.load(f).get("seen", []))


def save_seen(seen: set[str]) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump({"seen": sorted(seen)}, f, indent=2)


def flight_key(flight: dict) -> str:
    return f"{flight['airline']}|{flight['origin']}|{flight['destination']}|{flight['date']}"


def filter_new(flights: list[dict]) -> tuple[list[dict], set[str]]:
    """Returns only flights not seen before, plus the updated seen set."""
    seen = load_seen()
    new_flights = [f for f in flights if flight_key(f) not in seen]
    updated_seen = seen | {flight_key(f) for f in new_flights}
    return new_flights, updated_seen
