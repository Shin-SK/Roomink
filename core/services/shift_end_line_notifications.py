from django.db import transaction
from django.utils import timezone

from core.models import LineNotificationLog, ShiftAssignment, Store
from core.services.business_datetime import build_business_interval
from core.services.line_notify import (
    operations_push_is_configured,
    send_line_operations_push,
)
from core.services.shift_end_alerts import evaluate_shift_end_alerts


def _message_for_alert(item):
    return (
        "【Roomink 受付終了確認】\n"
        f"{item['cast_name']}さんのシフト終了70分前です。\n"
        f"終了予定: {item['shift_end_time_extended']}\n"
        f"本日の予約: {item['valid_order_count']}件\n"
        f"対応済み売上: ¥{item['done_sales']:,}\n"
        "この先の予約がないため、受付終了をご確認ください。"
    )


def send_shift_end_line_alerts(store, reference_at=None):
    """70分前アラートを同期し、未送信のOPENアラートを運営LINEへ送る。"""
    reference_at = reference_at or timezone.now()
    evaluated = evaluate_shift_end_alerts(store, reference_at=reference_at)
    result = {
        "open": len(evaluated["open_alerts"]),
        "sent": 0,
        "failed": 0,
        "configuration_missing": 0,
    }

    for item in evaluated["open_alerts"]:
        # 外部送信まで同じシフト行をロックする。二重起動したSchedulerはここで
        # 直列化され、後続側は確定済みの送信ログを見て何もしない。
        with transaction.atomic():
            locked_store = Store.objects.select_for_update().filter(pk=store.pk).first()
            if locked_store is None or not operations_push_is_configured(locked_store):
                result["configuration_missing"] += 1
                continue
            shift = (
                ShiftAssignment.objects.select_for_update()
                .select_related("cast")
                .filter(pk=item["shift_id"], store=locked_store)
                .first()
            )
            if shift is None:
                continue
            _, shift_end = build_business_interval(
                shift.date,
                shift.start_time,
                shift.end_time,
                end_day_offset=shift.end_day_offset,
                timezone_name=locked_store.timezone,
            )
            if reference_at >= shift_end:
                continue
            if LineNotificationLog.objects.filter(
                shift_assignment=shift,
                notification_type=LineNotificationLog.NotificationType.SHIFT_END_70,
                status=LineNotificationLog.Status.SENT,
            ).exists():
                continue

            shift.cast.store = locked_store
            log = send_line_operations_push(
                locked_store,
                shift.cast,
                _message_for_alert(item),
                shift,
                LineNotificationLog.NotificationType.SHIFT_END_70,
            )
        if log and log.status == LineNotificationLog.Status.SENT:
            result["sent"] += 1
        elif log:
            result["failed"] += 1

    return result
