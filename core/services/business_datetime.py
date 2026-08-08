import re
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_BUSINESS_DAY_BOUNDARY_HOUR = 5
MAX_EXTENDED_HOUR = 29
_EXTENDED_TIME_PATTERN = re.compile(r"^(\d{2}):(\d{2})$")


class BusinessDateTimeError(ValueError):
    """営業日時として扱えない入力。"""


def _validate_day_offset(day_offset):
    if isinstance(day_offset, bool) or day_offset not in (0, 1):
        raise BusinessDateTimeError("day_offsetは0または1で指定してください。")


def _validate_max_extended_hour(max_extended_hour):
    if (
        isinstance(max_extended_hour, bool)
        or not isinstance(max_extended_hour, int)
        or not 0 <= max_extended_hour <= 47
    ):
        raise BusinessDateTimeError("max_extended_hourは0から47の整数で指定してください。")


def _validate_boundary_hour(boundary_hour):
    if (
        isinstance(boundary_hour, bool)
        or not isinstance(boundary_hour, int)
        or not 0 <= boundary_hour <= 23
    ):
        raise BusinessDateTimeError("boundary_hourは0から23の整数で指定してください。")


def _coerce_timezone(timezone_name):
    if isinstance(timezone_name, str):
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise BusinessDateTimeError("有効なタイムゾーンを指定してください。") from exc
    if isinstance(timezone_name, tzinfo):
        return timezone_name
    raise BusinessDateTimeError("有効なタイムゾーンを指定してください。")


def _validate_local_time(local_time):
    if not isinstance(local_time, time):
        raise BusinessDateTimeError("時刻はdatetime.timeで指定してください。")
    if local_time.tzinfo is not None:
        raise BusinessDateTimeError("ローカル時刻にはタイムゾーンを付けないでください。")
    if local_time.second or local_time.microsecond:
        raise BusinessDateTimeError("時刻は分単位で指定してください。")


def _aware_local_datetime(local_date, local_time, target_timezone):
    naive = datetime.combine(local_date, local_time)
    fold_zero = naive.replace(tzinfo=target_timezone, fold=0)
    fold_one = naive.replace(tzinfo=target_timezone, fold=1)

    def round_trips(candidate):
        restored = candidate.astimezone(timezone.utc).astimezone(target_timezone)
        return restored.replace(tzinfo=None) == naive

    valid_zero = round_trips(fold_zero)
    valid_one = round_trips(fold_one)
    if not valid_zero and not valid_one:
        raise BusinessDateTimeError("存在しないローカル時刻です。")
    if (
        valid_zero
        and valid_one
        and fold_zero.utcoffset() != fold_one.utcoffset()
    ):
        raise BusinessDateTimeError("夏時間の切り替えで重複するローカル時刻です。")
    return fold_zero if valid_zero else fold_one


def parse_extended_time(value, max_extended_hour=MAX_EXTENDED_HOUR):
    """HH:MMを通常時刻と翌日offsetへ変換する。"""
    _validate_max_extended_hour(max_extended_hour)
    if not isinstance(value, str):
        raise BusinessDateTimeError("時刻はHH:MM形式で指定してください。")

    match = _EXTENDED_TIME_PATTERN.fullmatch(value)
    if not match:
        raise BusinessDateTimeError("時刻はHH:MM形式で指定してください。")

    hour = int(match.group(1))
    minute = int(match.group(2))
    total_minutes = hour * 60 + minute
    if minute > 59 or total_minutes > max_extended_hour * 60:
        raise BusinessDateTimeError(
            f"時刻は00:00から{max_extended_hour:02d}:00までで指定してください。"
        )

    day_offset = hour // 24
    _validate_day_offset(day_offset)
    return time(hour=hour % 24, minute=minute), day_offset


def format_extended_time(
    local_time,
    day_offset=0,
    max_extended_hour=MAX_EXTENDED_HOUR,
):
    """通常時刻と翌日offsetをHH:MMへ変換する。"""
    _validate_local_time(local_time)
    _validate_day_offset(day_offset)
    _validate_max_extended_hour(max_extended_hour)

    extended_hour = local_time.hour + 24 * day_offset
    total_minutes = extended_hour * 60 + local_time.minute
    if total_minutes > max_extended_hour * 60:
        raise BusinessDateTimeError(
            f"時刻は00:00から{max_extended_hour:02d}:00までで指定してください。"
        )
    return f"{extended_hour:02d}:{local_time.minute:02d}"


def build_store_datetime(
    business_date,
    local_time,
    day_offset=0,
    timezone_name="Asia/Tokyo",
):
    """営業日・ローカル時刻・offsetからtimezone-aware datetimeを作る。"""
    if not isinstance(business_date, date) or isinstance(business_date, datetime):
        raise BusinessDateTimeError("business_dateはdatetime.dateで指定してください。")
    _validate_local_time(local_time)
    _validate_day_offset(day_offset)
    target_timezone = _coerce_timezone(timezone_name)
    local_date = business_date + timedelta(days=day_offset)
    return _aware_local_datetime(local_date, local_time, target_timezone)


def build_business_interval(
    business_date,
    start_time,
    end_time,
    start_day_offset=0,
    end_day_offset=0,
    timezone_name="Asia/Tokyo",
):
    """営業日基準の半開区間[start_at, end_at)を作る。"""
    start_at = build_store_datetime(
        business_date,
        start_time,
        day_offset=start_day_offset,
        timezone_name=timezone_name,
    )
    end_at = build_store_datetime(
        business_date,
        end_time,
        day_offset=end_day_offset,
        timezone_name=timezone_name,
    )
    if end_at <= start_at:
        raise BusinessDateTimeError("終了日時は開始日時より後にしてください。")
    return start_at, end_at


def business_date_for_datetime(
    value,
    timezone_name="Asia/Tokyo",
    boundary_hour=DEFAULT_BUSINESS_DAY_BOUNDARY_HOUR,
):
    """aware datetimeが属する営業日を返す。境界時刻ちょうどから次営業日。"""
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise BusinessDateTimeError("timezone-aware datetimeを指定してください。")
    _validate_boundary_hour(boundary_hour)
    target_timezone = _coerce_timezone(timezone_name)
    local_value = value.astimezone(target_timezone)
    if local_value.time().replace(tzinfo=None) < time(boundary_hour, 0):
        return local_value.date() - timedelta(days=1)
    return local_value.date()


def business_day_range(
    business_date,
    timezone_name="Asia/Tokyo",
    boundary_hour=DEFAULT_BUSINESS_DAY_BOUNDARY_HOUR,
):
    """営業日の検索用半開区間[start_at, end_at)を返す。"""
    _validate_boundary_hour(boundary_hour)
    boundary_time = time(boundary_hour, 0)
    start_at = build_store_datetime(
        business_date,
        boundary_time,
        timezone_name=timezone_name,
    )
    end_at = build_store_datetime(
        business_date + timedelta(days=1),
        boundary_time,
        timezone_name=timezone_name,
    )
    return start_at, end_at


def intervals_overlap(start_a, end_a, start_b, end_b):
    """半開区間同士が重なるかを返す。境界が接するだけなら重複しない。"""
    values = (start_a, end_a, start_b, end_b)
    if not all(isinstance(value, datetime) for value in values):
        raise BusinessDateTimeError("区間はdatetimeで指定してください。")
    try:
        if end_a <= start_a or end_b <= start_b:
            raise BusinessDateTimeError("終了日時は開始日時より後にしてください。")
        return start_a < end_b and start_b < end_a
    except TypeError as exc:
        raise BusinessDateTimeError(
            "比較するdatetimeのタイムゾーン形式を統一してください。"
        ) from exc
