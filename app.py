import logging
import threading

from flask import Flask, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

import config
from scraper import scrape_bulletin
from calculator import calculate_changes, estimate_arrival
from state_manager import is_new_bulletin, update_state, load_state
from notifier import format_bulletin_message, send_telegram, send_error_notification

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route("/health")
def health():
    state = load_state()
    return jsonify({
        "status": "ok",
        "last_checked": state.get("last_checked"),
        "last_bulletin_month": state.get("last_bulletin_month"),
    })


@app.route("/state")
def show_state():
    """Debug: show full state data."""
    state = load_state()
    return jsonify(state)


@app.route("/check", methods=["GET", "POST"])
def manual_check():
    """Manually trigger a bulletin check."""
    try:
        result = check_bulletin(force=True)
        return jsonify({"status": "ok", "result": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/seed", methods=["GET", "POST"])
def seed_history():
    """One-time: seed history with past 7 months of bulletins."""
    try:
        from seed_history import seed
        seed()
        return jsonify({"status": "ok", "message": "Seeded 7 months of history"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def check_bulletin(force: bool = False) -> str:
    """Check for new Visa Bulletin and send notification if new."""
    try:
        logger.info("Starting bulletin check...")
        bulletin = scrape_bulletin()
        bulletin_month = bulletin["bulletin_month"]

        if not force and not is_new_bulletin(bulletin_month):
            logger.info(f"Bulletin {bulletin_month} already processed, skipping")
            return f"Already processed: {bulletin_month}"

        logger.info(f"New bulletin detected: {bulletin_month}")

        # Get previous data for comparison
        state = load_state()
        previous_entry = state["history"][0] if state["history"] else None

        # Calculate changes
        changes = calculate_changes(bulletin, previous_entry)

        # Update state (saves new entry to history)
        updated_state, _ = update_state(bulletin)

        # Estimate arrival
        estimate = estimate_arrival(updated_state["history"])

        # Format and send message
        message = format_bulletin_message(
            bulletin_month=bulletin_month,
            bulletin_url=bulletin["bulletin_url"],
            changes=changes,
            estimate=estimate,
        )
        send_telegram(message)
        logger.info("Bulletin check complete, notification sent")
        return f"New bulletin processed: {bulletin_month}"

    except Exception as e:
        logger.error(f"Bulletin check failed: {e}", exc_info=True)
        send_error_notification(str(e))
        raise


def start_scheduler():
    """Start the APScheduler for daily checks."""
    tz = pytz.timezone(config.TIMEZONE)
    # Convert KST hour to UTC for the cron trigger
    scheduler = BackgroundScheduler(timezone=tz)
    scheduler.add_job(
        check_bulletin,
        CronTrigger(hour=config.CHECK_HOUR_KST, minute=0, timezone=tz),
        id="bulletin_check",
        name="Daily Visa Bulletin Check",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        f"Scheduler started: daily check at {config.CHECK_HOUR_KST}:00 {config.TIMEZONE}"
    )


# Start scheduler when module loads (works with gunicorn --preload)
start_scheduler()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT)
