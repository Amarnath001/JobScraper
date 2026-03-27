from datetime import date, datetime
from zoneinfo import ZoneInfo


def get_timezone(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def now_in_timezone(tz_name: str) -> datetime:
    return datetime.now(get_timezone(tz_name))


def today_in_timezone(tz_name: str) -> date:
    return now_in_timezone(tz_name).date()


def start_of_day_local(d: date, tz_name: str) -> datetime:
    tz = get_timezone(tz_name)
    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=tz)


def end_of_day_local(d: date, tz_name: str) -> datetime:
    tz = get_timezone(tz_name)
    return datetime(d.year, d.month, d.day, 23, 59, 59, 999999, tzinfo=tz)
