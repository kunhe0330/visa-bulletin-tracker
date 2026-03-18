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
        f"\U0001f4cb 미국 비자 Bulletin 업데이트 ({bulletin_month})",
        "",
        "━━━━━━━━━━━━━━━━━━━━━",
        "\U0001f4cc Final Action Dates (비자 발급 기준)",
        "━━━━━━━━━━━━━━━━━━━━━",
        "▸ EB-3 Professionals/Skilled Workers",
        f'  현재 문호: {fa["eb3_professionals"]["current_date"]}',
        f'  전월 대비: {fa["eb3_professionals"]["change"]}',
        f'  내 PD까지 남은 기간: {fa["eb3_professionals"]["remaining"]}',
        "",
        "▸ EB-3 Other Workers",
        f'  현재 문호: {fa["eb3_other_workers"]["current_date"]}',
        f'  전월 대비: {fa["eb3_other_workers"]["change"]}',
        f'  내 PD까지 남은 기간: {fa["eb3_other_workers"]["remaining"]}',
        "",
        "━━━━━━━━━━━━━━━━━━━━━",
        "\U0001f4cc Dates for Filing (접수 가능 기준)",
        "━━━━━━━━━━━━━━━━━━━━━",
        "▸ EB-3 Professionals/Skilled Workers",
        f'  현재 문호: {df["eb3_professionals"]["current_date"]}',
        f'  전월 대비: {df["eb3_professionals"]["change"]}',
        f'  내 PD까지 남은 기간: {df["eb3_professionals"]["remaining"]}',
        "",
        "▸ EB-3 Other Workers",
        f'  현재 문호: {df["eb3_other_workers"]["current_date"]}',
        f'  전월 대비: {df["eb3_other_workers"]["change"]}',
        f'  내 PD까지 남은 기간: {df["eb3_other_workers"]["remaining"]}',
    ]

    if estimate:
        lines += [
            "",
            "━━━━━━━━━━━━━━━━━━━━━",
            "\U0001f4ca 도달 예상 (최근 6개월 평균 기준)",
            f"  Final Action 기준 예상 도달: {estimate}",
            "  ※ 단순 추정치이며 실제와 다를 수 있습니다.",
        ]

    lines += [
        "",
        f"\U0001f517 원문: {bulletin_url}",
    ]

    return "\n".join(lines)


def send_error_notification(error_msg: str):
    """Send error notification via Telegram."""
    message = f"\u26a0\ufe0f Visa Bulletin 확인 실패: {error_msg}\n수동 확인 필요."
    send_telegram(message)
