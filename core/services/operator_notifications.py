import logging
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.mail import send_mail

from core.models import OperatorNotification


logger = logging.getLogger(__name__)


def _public_booking_text(order):
    local_start = order.start.astimezone(ZoneInfo(order.store.timezone))
    local_end = order.end.astimezone(ZoneInfo(order.store.timezone))
    customer_name = order.customer.display_name or order.customer.phone
    date_label = local_start.strftime("%Y年%m月%d日")
    time_label = f"{local_start:%H:%M}〜{local_end:%H:%M}"
    title = f"Web予約が入りました（{local_start:%m/%d %H:%M}）"
    message = (
        f"{customer_name}様／{order.cast.name}／"
        f"{order.course_name}／{date_label} {time_label}"
    )
    return title, message, date_label, time_label, customer_name


def notify_public_booking_created(order):
    """Web予約成立をアプリ内へ残し、設定済みなら店舗へメールする。

    メール配送の障害で予約そのものを失敗させない。アプリ内通知は必ず先に保存する。
    """
    title, message, date_label, time_label, customer_name = _public_booking_text(order)
    notification = OperatorNotification.objects.create(
        store=order.store,
        kind=OperatorNotification.Kind.PUBLIC_BOOKING,
        order=order,
        title=title,
        message=message,
        target_path=f"/op/schedule?date={order.start.astimezone(ZoneInfo(order.store.timezone)):%Y-%m-%d}&highlight={order.id}",
    )

    recipient = (order.store.public_booking_notification_email or "").strip()
    if not recipient:
        return notification

    frontend_url = (settings.FRONTEND_URL or "").rstrip("/")
    schedule_url = f"{frontend_url}{notification.target_path}" if frontend_url else ""
    body_lines = [
        f"{order.store.name}にWeb予約が入りました。",
        "",
        f"日時：{date_label} {time_label}",
        f"お客様：{customer_name}様",
        f"担当：{order.cast.name}",
        f"コース：{order.course_name}",
    ]
    if schedule_url:
        body_lines.extend(["", f"予約タイムライン：{schedule_url}"])
    body_lines.extend(["", "このメールはRoominkから自動送信されています。"])

    try:
        send_mail(
            subject=f"【Roomink】{title}",
            message="\n".join(body_lines),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            "Public booking email notification failed: store_id=%s order_id=%s",
            order.store_id,
            order.id,
        )
    return notification
