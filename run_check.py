"""Cron 진입점: Visa Bulletin을 1회만 확인하고 종료한다.

app.py(상시 웹서버 + APScheduler)와 달리 long-running 프로세스를 띄우지 않으므로
좀비 컨테이너가 될 여지가 없다. Railway cron 스케줄에서 매일 호출한다.

성공 시 exit 0, 실패 시 텔레그램 에러 알림 발송 후 exit 1.
"""
import logging
import sys

from scraper import scrape_bulletin
from calculator import calculate_changes, estimate_arrival
from state_manager import is_new_bulletin, update_state, load_state
from notifier import format_bulletin_message, send_telegram, send_error_notification

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_check")


def run_check(force: bool = False) -> str:
    """문호를 1회 확인하고 신규 bulletin이면 알림을 보낸다.

    force=False면 기존 스케줄러와 동일하게 last_bulletin_month가 바뀐 경우에만 발송.
    """
    bulletin = scrape_bulletin()
    bulletin_month = bulletin["bulletin_month"]

    if not force and not is_new_bulletin(bulletin_month):
        logger.info(f"Bulletin {bulletin_month} already processed, skipping")
        return f"Already processed: {bulletin_month}"

    logger.info(f"New bulletin detected: {bulletin_month}")

    state = load_state()
    previous_entry = state["history"][0] if state["history"] else None

    changes = calculate_changes(bulletin, previous_entry)
    updated_state, _ = update_state(bulletin)
    estimate = estimate_arrival(updated_state["history"])

    message = format_bulletin_message(
        bulletin_month=bulletin_month,
        bulletin_url=bulletin["bulletin_url"],
        changes=changes,
        estimate=estimate,
    )
    send_telegram(message)
    logger.info("Check complete, notification sent")
    return f"New bulletin processed: {bulletin_month}"


if __name__ == "__main__":
    force = "--force" in sys.argv
    try:
        result = run_check(force=force)
        logger.info(f"Result: {result}")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Check failed: {e}", exc_info=True)
        send_error_notification(str(e))
        sys.exit(1)
