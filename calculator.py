from datetime import date
from typing import Union

import config


def _date_diff_description(old_date, new_date) -> str:
    """Calculate difference between two bulletin dates and return description."""
    # Handle special values
    if new_date == "C":
        if old_date == "C":
            return "변동 없음 (Current 유지)"
        return "Current로 변경!"
    if new_date == "U":
        if old_date == "U":
            return "변동 없음 (Unavailable 유지)"
        return "Unavailable로 변경"
    if old_date == "C":
        return f"후퇴 (Current → {_format_date(new_date)})"
    if old_date == "U":
        return f"개방 (Unavailable → {_format_date(new_date)})"

    delta_days = (new_date - old_date).days
    if delta_days == 0:
        return "변동 없음"
    elif delta_days > 0:
        return f"▲ {_days_to_readable(delta_days)} 진전"
    else:
        return f"▼ {_days_to_readable(abs(delta_days))} 후퇴"


def _days_to_readable(days: int) -> str:
    """Convert days to readable Korean string."""
    if days < 30:
        return f"{days}일"
    months = days // 30
    remaining_days = days % 30
    if remaining_days == 0:
        return f"{months}개월"
    return f"{months}개월 {remaining_days}일"


def _format_date(d) -> str:
    """Format date for display."""
    if d == "C":
        return "Current (제한 없음)"
    if d == "U":
        return "Unavailable"
    if isinstance(d, date):
        return d.strftime("%Y년 %m월 %d일")
    return str(d)


def _remaining_to_priority(bulletin_date, priority_date: date = None) -> str:
    """Calculate remaining period from bulletin date to user's priority date."""
    if priority_date is None:
        priority_date = config.PRIORITY_DATE

    if bulletin_date == "C":
        return "문호 도달 완료! (Current)"
    if bulletin_date == "U":
        return "현재 비자 발급 중단 (Unavailable)"

    if bulletin_date >= priority_date:
        return "문호 도달 완료! (내 PD 이전 날짜까지 도달)"

    delta_days = (priority_date - bulletin_date).days
    return f"약 {_days_to_readable(delta_days)} 남음"


def estimate_arrival(history: list, priority_date: date = None) -> str:
    """Estimate when Final Action date will reach priority date.

    Uses average monthly progress from the last 6 months of history.
    """
    if priority_date is None:
        priority_date = config.PRIORITY_DATE

    # Need at least 2 data points
    if len(history) < 2:
        return "데이터 부족 (최소 2개월 이력 필요)"

    # Use up to last 7 entries to get 6 monthly deltas
    recent = history[:7]  # history is newest-first
    recent.reverse()  # oldest-first for calculation

    deltas = []
    for i in range(1, len(recent)):
        old_fa = recent[i - 1].get("final_action", {}).get("eb3_professionals")
        new_fa = recent[i].get("final_action", {}).get("eb3_professionals")
        if old_fa in ("C", "U") or new_fa in ("C", "U"):
            continue
        old_d = _parse_stored_date(old_fa)
        new_d = _parse_stored_date(new_fa)
        if old_d and new_d:
            deltas.append((new_d - old_d).days)

    if not deltas:
        return "진전 데이터 부족"

    avg_days_per_month = sum(deltas) / len(deltas)
    if avg_days_per_month <= 0:
        return "최근 진전 없음 (추정 불가)"

    # Get current final action date
    latest_fa = history[0].get("final_action", {}).get("eb3_professionals")
    if latest_fa == "C":
        return "이미 Current"
    if latest_fa == "U":
        return "추정 불가 (Unavailable)"

    current_date = _parse_stored_date(latest_fa)
    if not current_date:
        return "추정 불가"

    remaining_days = (priority_date - current_date).days
    if remaining_days <= 0:
        return "이미 도달!"

    months_needed = remaining_days / avg_days_per_month
    from datetime import timedelta
    estimated_date = date.today() + timedelta(days=months_needed * 30)

    return (
        f"약 {estimated_date.strftime('%Y년 %m월')}경 "
        f"(월평균 {avg_days_per_month:.0f}일 진전 기준)"
    )


def _parse_stored_date(val) -> date:
    """Parse a date from stored state (YYYY-MM-DD string or date object)."""
    if isinstance(val, date):
        return val
    if isinstance(val, str) and val not in ("C", "U"):
        try:
            return date.fromisoformat(val)
        except ValueError:
            return None
    return None


def calculate_changes(new_data: dict, old_data: dict = None) -> dict:
    """Calculate all changes between new and old bulletin data.

    Returns dict with display-ready strings for each category.
    """
    result = {}

    for table_key in ("final_action", "dates_for_filing"):
        result[table_key] = {}
        for cat_key in ("eb3_professionals", "eb3_other_workers"):
            new_val = new_data[table_key][cat_key]

            if old_data and table_key in old_data and cat_key in old_data[table_key]:
                old_val = old_data[table_key][cat_key]
                # Convert stored string dates to date objects
                old_val = _parse_stored_date(old_val) if isinstance(old_val, str) and old_val not in ("C", "U") else old_val
                change_str = _date_diff_description(old_val, new_val)
            else:
                change_str = "이전 데이터 없음 (첫 확인)"

            remaining = _remaining_to_priority(new_val)

            result[table_key][cat_key] = {
                "current_date": _format_date(new_val),
                "change": change_str,
                "remaining": remaining,
            }

    return result
