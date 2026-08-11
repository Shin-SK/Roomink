from datetime import timedelta

from core.models import Order, Room, ShiftAssignment
from core.services.business_datetime import (
    BusinessDateTimeError,
    build_business_interval,
    intervals_overlap,
)


def _preferred_area_rank(cast, room):
    room_area = (room.area_name or "").strip().casefold()
    if not room_area:
        return None
    for rank in range(1, 6):
        preferred = (getattr(cast, f"preferred_area_{rank}", "") or "").strip().casefold()
        if preferred and preferred == room_area:
            return rank
    return None


def suggest_room_for_shift(
    store,
    cast,
    date,
    start_time,
    end_time,
    end_day_offset=0,
    exclude_shift_id=None,
):
    """空室の中からキャストの希望エリア順位を優先して1室選ぶ。"""
    start_at, end_at = build_business_interval(
        date,
        start_time,
        end_time,
        end_day_offset=end_day_offset,
        timezone_name=store.timezone,
    )
    rooms = list(Room.objects.filter(store=store).order_by("sort_order", "id"))
    if not rooms:
        return None

    blocked_room_ids = set(
        Order.objects.filter(
            store=store,
            room__isnull=False,
            status__in=Order.ACTIVE_STATUSES,
            start__lt=end_at,
            end__gt=start_at,
        ).values_list("room_id", flat=True)
    )

    shifts = ShiftAssignment.objects.filter(
        store=store,
        date__range=(date - timedelta(days=1), date + timedelta(days=1)),
    ).select_related("room")
    if exclude_shift_id:
        shifts = shifts.exclude(pk=exclude_shift_id)
    for shift in shifts:
        try:
            existing_start, existing_end = build_business_interval(
                shift.date,
                shift.start_time,
                shift.end_time,
                end_day_offset=shift.end_day_offset,
                timezone_name=store.timezone,
            )
        except BusinessDateTimeError:
            continue
        if intervals_overlap(start_at, end_at, existing_start, existing_end):
            blocked_room_ids.add(shift.room_id)

    available = [room for room in rooms if room.id not in blocked_room_ids]
    if not available:
        return None

    available.sort(key=lambda room: (
        _preferred_area_rank(cast, room) or 999,
        room.sort_order,
        room.id,
    ))
    return available[0]
