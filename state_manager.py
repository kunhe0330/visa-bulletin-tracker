import json
import os
import logging
from datetime import date, datetime
from typing import Optional

import config

logger = logging.getLogger(__name__)


def _json_serializer(obj):
    """JSON serializer for date objects."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def load_state() -> dict:
    """Load state from JSON file."""
    if not os.path.exists(config.STATE_FILE):
        return {
            "last_checked": None,
            "last_bulletin_month": None,
            "last_bulletin_url": None,
            "history": [],
        }
    try:
        with open(config.STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load state file: {e}")
        return {
            "last_checked": None,
            "last_bulletin_month": None,
            "last_bulletin_url": None,
            "history": [],
        }


def save_state(state: dict):
    """Save state to JSON file."""
    os.makedirs(os.path.dirname(config.STATE_FILE), exist_ok=True)
    with open(config.STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, default=_json_serializer, indent=2, ensure_ascii=False)
    logger.info("State saved successfully")


def _serialize_dates(data: dict) -> dict:
    """Convert date objects to ISO format strings for storage."""
    result = {}
    for key, val in data.items():
        if isinstance(val, date):
            result[key] = val.isoformat()
        elif val in ("C", "U"):
            result[key] = val
        else:
            result[key] = str(val)
    return result


def update_state(bulletin_data: dict) -> tuple[dict, Optional[dict]]:
    """Update state with new bulletin data.

    Returns (state, previous_entry_or_None).
    previous_entry is the last history entry before this update (for comparison).
    """
    state = load_state()
    now = datetime.now().isoformat()

    previous_entry = None
    if state["history"]:
        previous_entry = state["history"][0]

    new_entry = {
        "bulletin_month": bulletin_data["bulletin_month"],
        "checked_at": now,
        "final_action": _serialize_dates(bulletin_data["final_action"]),
        "dates_for_filing": _serialize_dates(bulletin_data["dates_for_filing"]),
    }

    # Insert at the beginning (newest first)
    state["history"].insert(0, new_entry)
    state["last_checked"] = now
    state["last_bulletin_month"] = bulletin_data["bulletin_month"]
    state["last_bulletin_url"] = bulletin_data["bulletin_url"]

    save_state(state)
    return state, previous_entry


def is_new_bulletin(bulletin_month: str) -> bool:
    """Check if this bulletin month is new (not yet processed)."""
    state = load_state()
    return state.get("last_bulletin_month") != bulletin_month
