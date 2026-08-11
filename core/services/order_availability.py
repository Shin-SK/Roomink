from datetime import timedelta
from zoneinfo import ZoneInfo

from core.models import CastUnavailableTime, Order, ShiftAssignment
from core.services.business_datetime import (
    build_business_interval,
    business_date_for_datetime,
    format_extended_time,
    intervals_overlap,
)


def find_covering_shift(store, cast, start_at, end_at):
    """予約区間全体を含む出勤シフトを返す。"""
    local_start = start_at.astimezone(ZoneInfo(store.timezone))
    business_date = business_date_for_datetime(start_at, store.timezone)
    candidate_dates = {business_date, local_start.date()}
    shifts = ShiftAssignment.objects.filter(
        store=store,
        cast=cast,
        date__range=(min(candidate_dates), max(candidate_dates)),
        is_absent=False,
    ).order_by("date", "start_time")

    for shift in shifts:
        shift_start, shift_end = build_business_interval(
            shift.date,
            shift.start_time,
            shift.end_time,
            end_day_offset=shift.end_day_offset,
            timezone_name=store.timezone,
        )
        if shift_start <= start_at and end_at <= shift_end:
            return shift
    return None


def cast_has_order_conflict(cast, start_at, end_at, exclude_order_id=None):
    """既存予約後のキャスト別インターバルを含めて重複を判定する。"""
    interval = timedelta(minutes=cast.interval_minutes or 0)
    orders = Order.objects.filter(
        cast=cast,
        status__in=Order.ACTIVE_STATUSES,
        start__lt=end_at,
        end__gt=start_at - interval,
    )
    if exclude_order_id is not None:
        orders = orders.exclude(pk=exclude_order_id)

    return any(
        intervals_overlap(
            existing.start,
            existing.end + interval,
            start_at,
            end_at,
        )
        for existing in orders
    )


def cast_has_unavailable_time_conflict(
    cast,
    start_at,
    end_at,
    exclude_unavailable_time_id=None,
):
    """キャストの予約不可時間と半開区間が重なるかを返す。"""
    unavailable_times = CastUnavailableTime.objects.filter(
        cast=cast,
        start_at__lt=end_at,
        end_at__gt=start_at,
    )
    if exclude_unavailable_time_id is not None:
        unavailable_times = unavailable_times.exclude(pk=exclude_unavailable_time_id)
    return unavailable_times.exists()


def build_available_order_slots(
    store,
    cast,
    business_date,
    slot_minutes=30,
    duration_minutes=None,
    not_before=None,
):
    """営業日内のシフトから、予約可能な開始時刻を作る。

    duration_minutesを指定した場合は、その施術時間全体が空いている開始時刻だけを返す。
    """
    shifts = ShiftAssignment.objects.filter(
        store=store,
        cast=cast,
        date=business_date,
        is_absent=False,
    ).order_by("start_time")
    shift_intervals = [
        build_business_interval(
            shift.date,
            shift.start_time,
            shift.end_time,
            end_day_offset=shift.end_day_offset,
            timezone_name=store.timezone,
        )
        for shift in shifts
    ]
    if not shift_intervals:
        return []

    window_start = min(start_at for start_at, _ in shift_intervals)
    window_end = max(end_at for _, end_at in shift_intervals)
    interval = timedelta(minutes=cast.interval_minutes or 0)
    orders = list(Order.objects.filter(
        cast=cast,
        status__in=Order.ACTIVE_STATUSES,
        start__lt=window_end,
        end__gt=window_start - interval,
    ))
    unavailable_times = list(CastUnavailableTime.objects.filter(
        cast=cast,
        start_at__lt=window_end,
        end_at__gt=window_start,
    ))
    timezone = ZoneInfo(store.timezone)
    step = timedelta(minutes=slot_minutes)
    duration = timedelta(minutes=duration_minutes or slot_minutes)
    slots_by_start = {}

    def display_time(value):
        local_value = value.astimezone(timezone)
        day_offset = (local_value.date() - business_date).days
        return format_extended_time(
            local_value.time().replace(tzinfo=None),
            day_offset,
        )

    for shift_start, shift_end in shift_intervals:
        slot_start = shift_start
        while slot_start + duration <= shift_end:
            slot_end = slot_start + duration
            conflict = any(
                intervals_overlap(
                    existing.start,
                    existing.end + interval,
                    slot_start,
                    slot_end,
                )
                for existing in orders
            )
            conflict = conflict or any(
                intervals_overlap(
                    unavailable.start_at,
                    unavailable.end_at,
                    slot_start,
                    slot_end,
                )
                for unavailable in unavailable_times
            )
            if not conflict and (not_before is None or slot_start > not_before):
                slots_by_start[slot_start] = {
                    "start": display_time(slot_start),
                    "end": display_time(slot_end),
                    "start_at": slot_start.isoformat(),
                    "end_at": slot_end.isoformat(),
                }
            slot_start += step

    return [slots_by_start[key] for key in sorted(slots_by_start)]
