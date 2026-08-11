from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

import holidays

from .contracts import MarketStatus

SHANGHAI = ZoneInfo("Asia/Shanghai")
NEW_YORK = ZoneInfo("America/New_York")


def _between(value: time, start: time, end: time) -> bool:
    return start <= value < end


def market_status(market: str, now: datetime | None = None) -> MarketStatus:
    current = now or datetime.now(UTC)
    if market in {"CN", "HK"}:
        local = current.astimezone(SHANGHAI)
        if local.weekday() >= 5:
            return "weekend"
        country = "CN" if market == "CN" else "HK"
        if local.date() in holidays.country_holidays(country, years=[local.year]):
            return "holiday"
        clock = local.time()
        morning_end = time(11, 30) if market == "CN" else time(12)
        afternoon_start = time(13)
        afternoon_end = time(15) if market == "CN" else time(16)
        if _between(clock, time(9, 30), morning_end) or _between(
            clock, afternoon_start, afternoon_end
        ):
            return "trading"
        return "closed"

    local = current.astimezone(NEW_YORK)
    if local.weekday() >= 5:
        return "weekend"
    clock = local.time()
    if market == "US":
        if local.date() in holidays.country_holidays("US", years=[local.year]):
            return "holiday"
        if _between(clock, time(4), time(9, 30)):
            return "pre_market"
        if _between(clock, time(9, 30), time(16)):
            return "trading"
        if _between(clock, time(16), time(20)):
            return "post_market"
        return "closed"
    if market in {"COMMODITY", "FX"}:
        return "trading" if _between(clock, time(0), time(23)) else "closed"
    return "unavailable"
