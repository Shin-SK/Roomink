from datetime import timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.models import Order, ShiftAssignment, ShiftEndAlert
from core.services.business_datetime import (
    business_date_for_datetime,
    build_business_interval,
    format_extended_time,
)


ALERT_LEAD_TIME = timedelta(minutes=70)


def _shift_orders(shift, shift_start, shift_end):
    return (
        Order.objects
        .filter(
            store=shift.store,
            cast=shift.cast,
            start__lt=shift_end,
            end__gt=shift_start,
        )
        .exclude(status=Order.Status.CANCELLED)
    )


def _serialize_alert(alert, shift_start, shift_end):
    orders = _shift_orders(alert.shift_assignment, shift_start, shift_end)
    done_sales = orders.filter(status=Order.Status.DONE).aggregate(
        total=Sum("total_price")
    )["total"] or 0
    return {
        "id": alert.id,
        "shift_id": alert.shift_assignment_id,
        "cast_id": alert.cast_id,
        "cast_name": alert.cast.name,
        "business_date": alert.shift_assignment.date.isoformat(),
        "shift_end_time_extended": format_extended_time(
            alert.shift_assignment.end_time,
            alert.shift_assignment.end_day_offset,
        ),
        "alert_at": alert.alert_at.isoformat(),
        "status": alert.status,
        "valid_order_count": orders.count(),
        "done_sales": done_sales,
        "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
        "created_at": alert.created_at.isoformat(),
    }


def evaluate_shift_end_alerts(store, reference_at=None):
    """現在営業日の70分前アラートを同期し、画面表示用データを返す。"""
    reference_at = reference_at or timezone.now()
    business_date = business_date_for_datetime(reference_at, store.timezone)
    shifts = list(
        ShiftAssignment.objects
        .filter(store=store, date=business_date, is_absent=False)
        .select_related("cast", "room", "store")
        .order_by("end_day_offset", "end_time", "id")
    )

    serialized = []
    for shift in shifts:
        shift_start, shift_end = build_business_interval(
            shift.date,
            shift.start_time,
            shift.end_time,
            end_day_offset=shift.end_day_offset,
            timezone_name=store.timezone,
        )
        alert_at = shift_end - ALERT_LEAD_TIME
        if reference_at < alert_at:
            continue

        with transaction.atomic():
            locked_shift = (
                ShiftAssignment.objects
                .select_for_update()
                .select_related("cast", "room", "store")
                .get(pk=shift.pk)
            )
            alert = ShiftEndAlert.objects.filter(
                shift_assignment=locked_shift,
            ).first()
            orders = _shift_orders(locked_shift, shift_start, shift_end)
            has_late_order = orders.filter(
                end__gt=alert_at,
                start__lt=shift_end,
            ).exists()

            if alert is None:
                if has_late_order or reference_at >= shift_end:
                    continue
                alert = ShiftEndAlert.objects.create(
                    store=store,
                    shift_assignment=locked_shift,
                    cast=locked_shift.cast,
                    alert_at=alert_at,
                )
            else:
                update_fields = []
                if alert.alert_at != alert_at:
                    alert.alert_at = alert_at
                    update_fields.append("alert_at")
                if has_late_order and alert.status == ShiftEndAlert.Status.OPEN:
                    alert.status = ShiftEndAlert.Status.RESOLVED
                    alert.resolved_at = reference_at
                    update_fields.extend(["status", "resolved_at"])
                elif (
                    not has_late_order
                    and reference_at < shift_end
                    and alert.status == ShiftEndAlert.Status.RESOLVED
                ):
                    alert.status = ShiftEndAlert.Status.OPEN
                    alert.resolved_at = None
                    update_fields.extend(["status", "resolved_at"])
                if update_fields:
                    alert.save(update_fields=[*update_fields, "updated_at"])

        serialized.append(_serialize_alert(alert, shift_start, shift_end))

    return {
        "open_alerts": [item for item in serialized if item["status"] == ShiftEndAlert.Status.OPEN],
        "resolved_alerts": [
            item for item in serialized if item["status"] == ShiftEndAlert.Status.RESOLVED
        ],
        "external_send_supported": bool(
            store.line_shift_end_alert_enabled
            and store.line_operations_recipient_id
        ),
    }
