"""Optimistic checks run while the caller holds the store/order locks."""
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import APIException

from core.models import OrderEditLog


class OrderEditConflict(APIException):
    status_code = 409
    default_detail = "予約が更新されています。入力内容は残しています。最新の予約を確認してから、もう一度変更してください。"
    default_code = "order_edit_conflict"


def require_current_order(order, expected_updated_at, *, required=False):
    if expected_updated_at is None and not required:
        return
    try:
        expected = parse_datetime(expected_updated_at) if isinstance(expected_updated_at, str) else expected_updated_at
    except (ValueError, TypeError):
        expected = None
    if expected is None or expected != order.updated_at:
        raise OrderEditConflict()


def order_edit_snapshot(order):
    # Deliberately exclude customer details and free-text notes.
    return {
        "reception_staff_id": order.reception_staff_id,
        "reception_staff_name": order.reception_staff_name,
        "option_ids": sorted(order.options.values_list("id", flat=True)),
        **{field: getattr(order, field) for field in (
            "course_price", "options_price", "extension_price",
            "nomination_fee_price", "discount_amount", "total_price",
            "payment_method", "card_include_options",
        )},
    }


def record_order_edit(order, before, actor, source):
    after = order_edit_snapshot(order)
    if before != after:
        OrderEditLog.objects.create(
            store=order.store, order=order, acted_by=actor, source=source,
            before=before, after=after,
        )
