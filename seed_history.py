"""One-time script to seed bulletin history from past 7 months."""
import logging
from scraper import scrape_bulletin
from state_manager import load_state, save_state

logging.basicConfig(level=logging.INFO)

PAST_BULLETINS = [
    "https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin/2026/visa-bulletin-for-october-2025.html",
    "https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin/2026/visa-bulletin-for-november-2025.html",
    "https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin/2026/visa-bulletin-for-december-2025.html",
    "https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin/2026/visa-bulletin-for-january-2026.html",
    "https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin/2026/visa-bulletin-for-february-2026.html",
    "https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin/2026/visa-bulletin-for-march-2026.html",
    "https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin/2026/visa-bulletin-for-april-2026.html",
]


def seed():
    history = []
    for url in PAST_BULLETINS:
        data = scrape_bulletin(url)
        entry = {
            "bulletin_month": data["bulletin_month"],
            "checked_at": "seed",
            "final_action": {
                "eb3_professionals": data["final_action"]["eb3_professionals"].isoformat()
                if hasattr(data["final_action"]["eb3_professionals"], "isoformat")
                else data["final_action"]["eb3_professionals"],
                "eb3_other_workers": data["final_action"]["eb3_other_workers"].isoformat()
                if hasattr(data["final_action"]["eb3_other_workers"], "isoformat")
                else data["final_action"]["eb3_other_workers"],
            },
            "dates_for_filing": {
                "eb3_professionals": data["dates_for_filing"]["eb3_professionals"].isoformat()
                if hasattr(data["dates_for_filing"]["eb3_professionals"], "isoformat")
                else data["dates_for_filing"]["eb3_professionals"],
                "eb3_other_workers": data["dates_for_filing"]["eb3_other_workers"].isoformat()
                if hasattr(data["dates_for_filing"]["eb3_other_workers"], "isoformat")
                else data["dates_for_filing"]["eb3_other_workers"],
            },
        }
        history.append(entry)
        print(f"Loaded: {data['bulletin_month']}")

    # Reverse so newest is first
    history.reverse()

    latest = history[0]
    state = {
        "last_checked": "2026-03-18T00:00:00",
        "last_bulletin_month": latest["bulletin_month"],
        "last_bulletin_url": PAST_BULLETINS[-1],
        "history": history,
    }
    save_state(state)
    print(f"\nSeeded {len(history)} months of history. Latest: {latest['bulletin_month']}")


if __name__ == "__main__":
    seed()
