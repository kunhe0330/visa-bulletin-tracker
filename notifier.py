import logging

import requests

import config

logger = logging.getLogger(__name__)


def send_telegram(message: str):
    """Send a message via Telegram Bot API."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not configured, skipping notification")
        return

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info("Telegram notification sent successfully")
    except requests.RequestException as e:
        logger.error(f"Failed to send Telegram notification: {e}")


def format_bulletin_message(
    bulletin_month: str,
    bulletin_url: str,
    changes: dict,
    estimate: str = None,
) -> str:
    """Format the bulletin update message in Korean."""
    fa = changes["final_action"]
    df = changes["dates_for_filing"]

    lines = [
        f"\U0001f4cb 비자 Bulletin 업데이트 ({bulletin_month})",
        "",
        "\U0001f4cc Final Action (비자 발급 기준)",
        f'  문호: {fa["eb3_professionals"]["current_date"]}',
        f'  전월 대비: {fa["eb3_professionals"]["change"]}',
        f'  내 PD까지: {fa["eb3_professionals"]["remaining"]}',
        "",
        "\U0001f4cc Dates for Filing (접수 기준)",
        f'  문호: {df["eb3_professionals"]["current_date"]}',
        f'  전월 대비: {df["eb3_professionals"]["change"]}',
        f'  내 PD까지: {df["eb3_professionals"]["remaining"]}',
    ]

    if estimate:
        lines += [
            "",
            f"\U0001f4ca 예상 도달: {estimate}",
        ]

    lines += [
        "",
        f"\U0001f517 {bulletin_url}",
    ]

    return "\n".join(lines)


def send_error_notification(error_msg: str):
    """Send error notification via Telegram."""
    message = f"\u26a0\ufe0f Visa Bulletin 확인 실패: {error_msg}\n수동 확인 필요."
    send_telegram(message)
