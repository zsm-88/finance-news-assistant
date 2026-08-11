from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

import holidays

from .contracts import FundMarketStatus

SHANGHAI = ZoneInfo("Asia/Shanghai")


@lru_cache(maxsize=8)
def _china_holidays(year: int) -> holidays.HolidayBase:
    return holidays.country_holidays("CN", years=[year])


def fund_market_status(now: datetime) -> FundMarketStatus:
    local = now.astimezone(SHANGHAI)
    if local.weekday() >= 5:
        return "weekend"
    if local.date() in _china_holidays(local.year):
        return "holiday"
    minute = local.hour * 60 + local.minute
    if 9 * 60 + 30 <= minute <= 11 * 60 + 30 or 13 * 60 <= minute <= 15 * 60:
        return "trading"
    return "closed"


def estimate_is_stale(
    as_of: datetime | None,
    now: datetime,
    stale_after_seconds: int,
) -> bool:
    if as_of is None:
        return True
    local_value = as_of.astimezone(SHANGHAI)
    local_now = now.astimezone(SHANGHAI)
    if local_value.date() != local_now.date():
        return True
    age_seconds = (now - as_of).total_seconds()
    if age_seconds < -60:
        return True
    return fund_market_status(now) == "trading" and age_seconds > stale_after_seconds
