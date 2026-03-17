ORIGINS = ["TLV", "HFA"]
DATES = ["2026-03-18", "2026-03-19", "2026-03-20", "2026-03-21", "2026-03-22"]
ADULTS = 2
INFANTS = 1

# European airports to search per airline (curated to known/likely routes)
ROUTES = {
    "elal": {
        # El Al flies internationally from TLV only
        "TLV": ["LHR", "LGW", "CDG", "AMS", "FRA", "BCN", "FCO", "ATH", "VIE", "ZRH", "BER", "MUC"],
        "HFA": [],
    },
    "arkia": {
        # Arkia operates charter/scheduled from TLV
        "TLV": ["LGW", "CDG", "ATH", "BCN", "FCO", "AMS", "VIE", "FRA"],
        "HFA": [],
    },
    "israir": {
        # Israir mainly charter from TLV
        "TLV": ["LGW", "CDG", "ATH", "BCN", "FCO"],
        "HFA": [],
    },
    "airhaifa": {
        # Air Haifa is domestic only — no European routes expected
        "TLV": [],
        "HFA": [],
    },
}
