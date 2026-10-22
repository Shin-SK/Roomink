"""勤務に紐づく打刻。営業日や報酬の算定とは独立させる。"""
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from core.models import ShiftAttendanceEvent
from core.services.business_datetime import business_date_for_datetime, build_business_interval


def can_clock_in(shift, now, start, end):
    today = business_date_for_datetime(now, shift.store.timezone, shift.store.business_day_boundary_hour)
    return (not shift.is_absent and not shift.clocked_in_at and now <= end
            and (shift.date == today or start <= now <= end))


def attendance_snapshot(shift):
    return {key: getattr(shift, key).isoformat() if getattr(shift, key) else None
            for key in ("clocked_in_at", "clocked_out_at")}


def save_attendance(shift, *, actor, action, clocked_in_at, clocked_out_at, reason=""):
    if clocked_out_at and (not clocked_in_at or clocked_out_at < clocked_in_at):
        raise ValidationError("退勤時刻は出勤時刻以降にしてください")
    before = attendance_snapshot(shift)
    shift.clocked_in_at = clocked_in_at
    shift.clocked_out_at = clocked_out_at
    after = attendance_snapshot(shift)
    if before == after:
        return
    if clocked_in_at:
        shift.is_absent = False
    shift.save(update_fields=["clocked_in_at", "clocked_out_at", "is_absent"])
    ShiftAttendanceEvent.objects.create(
        shift=shift, recorded_by=actor, action=action, before=before, after=after, reason=reason,
    )


def serialize_attendance(shift, *, include_history=False):
    start, end = build_business_interval(
        shift.date, shift.start_time, shift.end_time,
        start_day_offset=shift.start_day_offset, end_day_offset=shift.end_day_offset,
        timezone_name=shift.store.timezone,
    )
    now = timezone.now()
    alerts = []
    if not shift.is_absent and not shift.clocked_in_at and now > start:
        alerts.append("出勤未打刻")
    if shift.clocked_in_at and not shift.clocked_out_at and now > end:
        alerts.append("未退勤")
    if shift.clocked_in_at and abs((shift.clocked_in_at - start).total_seconds()) >= 3600:
        alerts.append("出勤が予定と1時間以上ずれています")
    if shift.clocked_out_at and abs((shift.clocked_out_at - end).total_seconds()) >= 3600:
        alerts.append("退勤が予定と1時間以上ずれています")
    data = {
        "id": shift.id, "date": shift.date.isoformat(), "cast_id": shift.cast_id, "cast_name": shift.cast.name,
        "scheduled_start": start, "scheduled_end": end,
        **attendance_snapshot(shift), "alerts": alerts,
        "is_absent": shift.is_absent,
        "can_clock_in": can_clock_in(shift, now, start, end),
    }
    if include_history:
        data["history"] = [{
            "id": event.id, "action": event.action, "before": event.before, "after": event.after,
            "reason": event.reason, "recorded_at": event.recorded_at,
            "recorded_by_name": event.recorded_by.username if event.recorded_by else "",
        } for event in shift.attendance_events.all()]
    return data
