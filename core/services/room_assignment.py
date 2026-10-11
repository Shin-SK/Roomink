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


def preferred_area_names(cast):
    """Return a cast's configured areas in priority order."""
    return [
        (getattr(cast, f"preferred_area_{rank}", "") or "").strip()
        for rank in range(1, 6)
        if (getattr(cast, f"preferred_area_{rank}", "") or "").strip()
    ]


def suggest_room_for_shift(
    store,
    cast,
    date,
    start_time,
    end_time,
    start_day_offset=0,
    end_day_offset=0,
    exclude_shift_id=None,
    area_name=None,
):
    """Pick an available room only from an explicitly permitted area.

    A shift must never silently spill into an unrequested area.  With an
    ``area_name`` the operator has made an explicit area choice; otherwise
    the cast's ranked preferred areas define the permitted set.  ``None``
    means that an operator must make the next decision.
    """
    start_at, end_at = build_business_interval(
        date,
        start_time,
        end_time,
        start_day_offset=start_day_offset,
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
                start_day_offset=shift.start_day_offset,
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

    requested_area = (area_name or "").strip().casefold()
    if requested_area:
        available = [
            room for room in available
            if (room.area_name or "").strip().casefold() == requested_area
        ]
    else:
        preferred_areas = {area.casefold() for area in preferred_area_names(cast)}
        if not preferred_areas:
            return None
        available = [
            room for room in available
            if (room.area_name or "").strip().casefold() in preferred_areas
        ]
    if not available:
        return None

    available.sort(key=lambda room: (
        _preferred_area_rank(cast, room) or 999,
        room.sort_order,
        room.id,
    ))
    return available[0]
