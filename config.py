ORIGINS = ["TLV", "HFA"]
DATES = ["2026-03-18", "2026-03-19", "2026-03-20", "2026-03-21", "2026-03-22"]
ADULTS = 2
INFANTS = 1

# All destinations to check (applied to all airlines — empty results are handled gracefully)
ALL_DESTINATIONS = [
    # London (all airports)
    "LHR",  # Heathrow
    "LGW",  # Gatwick
    "STN",  # Stansted
    "LTN",  # Luton
    "LCY",  # City
    # France
    "CDG",  # Paris Charles de Gaulle
    "ORY",  # Paris Orly
    # Germany
    "FRA",  # Frankfurt
    "MUC",  # Munich
    "BER",  # Berlin
    # Netherlands
    "AMS",  # Amsterdam
    # Spain
    "BCN",  # Barcelona
    "MAD",  # Madrid
    # Italy
    "FCO",  # Rome Fiumicino
    "MXP",  # Milan Malpensa
    # Greece
    "ATH",  # Athens
    # Cyprus
    "LCA",  # Larnaca
    # Austria
    "VIE",  # Vienna
    # Switzerland
    "ZRH",  # Zurich
    "GVA",  # Geneva
    # Poland
    "WAW",  # Warsaw
    # Hungary
    "BUD",  # Budapest
    # Bulgaria
    "SOF",  # Sofia
    # Romania
    "OTP",  # Bucharest
    # Georgia
    "TBS",  # Tbilisi
]

ROUTES = {
    "elal":     {"TLV": ALL_DESTINATIONS, "HFA": []},
    "arkia":    {"TLV": ALL_DESTINATIONS, "HFA": []},
    "israir":   {"TLV": ALL_DESTINATIONS, "HFA": []},
    "airhaifa": {"TLV": ["LCA", "ATH"], "HFA": ["LCA", "ATH"]},
}

# Positive control: one search per airline that should always return flights.
# If it returns nothing the scraper is broken — skip that airline for this run.
CONTROL_CHECKS = {
    "elal":     ("TLV", "ATH", "2026-04-30"),
    "arkia":    ("TLV", "ATH", "2026-04-30"),
    "israir":   ("TLV", "ATH", "2026-04-30"),
    "airhaifa": ("TLV", "LCA", "2026-03-20"),
}
