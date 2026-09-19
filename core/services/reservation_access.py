from datetime import timedelta

from django.conf import settings
from django.db.models import F
from django.utils import timezone

from core.models import Order, OrderGuestAccess, SmsLog


ACCESS_RETENTION = timedelta(days=30)


class GuestReservationState:
    REQUESTED = "REQUESTED"
    PAYMENT_REQUIRED = "PAYMENT_REQUIRED"
    CONFIRMED = "CONFIRMED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


def guest_reservation_state(order):
    if order.status == Order.Status.CANCELLED:
        return GuestReservationState.CANCELLED
    if order.status == Order.Status.REQUESTED:
        return GuestReservationState.REQUESTED
    if (
        order.payment_method == Order.PaymentMethod.CARD
        and order.card_payment_confirmed_at is None
    ):
        return GuestReservationState.PAYMENT_REQUIRED
    if order.status == Order.Status.IN_PROGRESS:
        return GuestReservationState.IN_PROGRESS
    if order.status in (Order.Status.PENDING_FINALIZE, Order.Status.DONE):
        return GuestReservationState.COMPLETED
    return GuestReservationState.CONFIRMED


def guest_state_copy(state):
    return {
        GuestReservationState.REQUESTED: {
            "label": "予約確認中",
            "title": "ご予約を受け付けました",
            "message": "店舗で予約内容を確認しています。確定までしばらくお待ちください。",
        },
        GuestReservationState.PAYMENT_REQUIRED: {
            "label": "仮予約・カード決済待ち",
            "title": "カード決済をお願いします",
            "message": "カード決済後、店舗での確認をもって本予約となります。",
        },
        GuestReservationState.CONFIRMED: {
            "label": "予約確定",
            "title": "ご予約が確定しました",
            "message": "以下の内容でご予約を承っています。",
        },
        GuestReservationState.IN_PROGRESS: {
            "label": "ご案内中",
            "title": "ご案内中です",
            "message": "現在の予約内容をご確認いただけます。",
        },
        GuestReservationState.COMPLETED: {
            "label": "ご利用済み",
            "title": "ご利用ありがとうございました",
            "message": "ご予約内容をご確認いただけます。",
        },
        GuestReservationState.CANCELLED: {
            "label": "キャンセル",
            "title": "ご予約はキャンセルされました",
            "message": "ご不明な点は店舗へ直接お問い合わせください。",
        },
    }[state]


def card_payment_amount(order):
    """外部決済画面へ顧客自身が入力するカード請求予定額。"""
    cash_due = 0
    if not order.card_include_options:
        cash_due = min(order.options_price, order.total_price)
    charge_base = max(0, order.total_price - cash_due)
    fee = round(charge_base * order.store.card_fee_rate / 100)
    return charge_base + fee, cash_due


def issue_order_guest_access(order):
    expires_at = max(order.end + ACCESS_RETENTION, timezone.now() + ACCESS_RETENTION)
    access, created = OrderGuestAccess.objects.get_or_create(
        order=order,
        defaults={"expires_at": expires_at},
    )
    if not created and access.expires_at < expires_at:
        access.expires_at = expires_at
        access.save(update_fields=["expires_at", "updated_at"])
    return access


def build_order_guest_url(order):
    base_url = settings.RESERVATION_LINK_BASE_URL
    if not base_url:
        return ""
    access = issue_order_guest_access(order)
    return f"{base_url}/r/{access.token}"


def get_valid_order_guest_access(token):
    if not token:
        return None
    now = timezone.now()
    return (
        OrderGuestAccess.objects
        .select_related("order__store", "order__cast", "order__room", "order__course")
        .prefetch_related("order__options", "order__sms_logs")
        .filter(
            token=token,
            invalidated_at__isnull=True,
            expires_at__gt=now,
        )
        .first()
    )


def mark_guest_access_opened(access, state):
    now = timezone.now()
    updates = {
        "last_opened_at": now,
        "last_seen_state": state,
        "last_seen_at": now,
        "open_count": F("open_count") + 1,
    }
    if access.first_opened_at is None:
        updates["first_opened_at"] = now
    OrderGuestAccess.objects.filter(pk=access.pk).update(**updates)


def _event_time(order, template_type):
    log = (
        order.sms_logs
        .filter(
            template_type=template_type,
            status__in=(SmsLog.Status.SENT, SmsLog.Status.DUMMY),
        )
        .order_by("sent_at", "id")
        .first()
    )
    return log.sent_at if log else None


def build_guest_timeline(order):
    events = [{
        "type": "RECEIVED",
        "label": "ご予約を受け付けました",
        "occurred_at": order.created_at,
    }]

    if order.payment_method == Order.PaymentMethod.CARD:
        requested_at = _event_time(order, SmsLog.TemplateType.CARD_PAYMENT_REQUEST)
        if requested_at:
            events.append({
                "type": "PAYMENT_REQUESTED",
                "label": "カード決済をご案内しました",
                "occurred_at": requested_at,
            })
        if order.card_payment_confirmed_at:
            events.append({
                "type": "PAYMENT_CONFIRMED",
                "label": "店舗がカード決済を確認しました",
                "occurred_at": order.card_payment_confirmed_at,
            })
            events.append({
                "type": "CONFIRMED",
                "label": "ご予約が確定しました",
                "occurred_at": order.card_payment_confirmed_at,
            })
    else:
        confirmed_at = _event_time(order, SmsLog.TemplateType.RESERVATION_CONFIRMATION)
        if confirmed_at:
            events.append({
                "type": "CONFIRMED",
                "label": "ご予約が確定しました",
                "occurred_at": confirmed_at,
            })

    if order.status == Order.Status.CANCELLED:
        cancelled_at = _event_time(order, SmsLog.TemplateType.RESERVATION_CANCELLED) or order.updated_at
        events.append({
            "type": "CANCELLED",
            "label": "ご予約がキャンセルされました",
            "occurred_at": cancelled_at,
        })

    return sorted(events, key=lambda event: event["occurred_at"])


def serialize_guest_reservation(access):
    order = access.order
    state = guest_reservation_state(order)
    copy = guest_state_copy(state)
    contact_phone = (
        order.store.phone_numbers
        .filter(is_active=True)
        .exclude(source_phone="")
        .order_by("id")
        .values_list("source_phone", flat=True)
        .first()
        or ""
    )
    contact_phone = contact_phone.strip()
    room_visible = (
        state in (
            GuestReservationState.CONFIRMED,
            GuestReservationState.IN_PROGRESS,
            GuestReservationState.COMPLETED,
        )
        and order.room_id is not None
    )
    payment_required = state == GuestReservationState.PAYMENT_REQUIRED
    payment_amount = 0
    cash_due = 0
    if order.payment_method == Order.PaymentMethod.CARD:
        payment_amount, cash_due = card_payment_amount(order)

    return {
        "state": state,
        "state_label": copy["label"],
        "title": copy["title"],
        "message": copy["message"],
        "store_name": order.store.name,
        "contact_phone": contact_phone,
        "start": order.start,
        "end": order.end,
        "cast_name": order.cast.name,
        "course_name": order.course_name,
        "total_price": order.total_price,
        "payment_method": order.payment_method,
        "payment_method_label": order.get_payment_method_display(),
        "payment_required": payment_required,
        "payment_url": order.store.card_payment_url if payment_required else "",
        "payment_amount": payment_amount,
        "cash_due_on_site": cash_due,
        "room_name": order.room.name if room_visible else "",
        "room_address": order.room.address if room_visible else "",
        "room_map_url": order.room.map_url if room_visible else "",
        "room_notice": order.room.sms_notice if room_visible else "",
        "timeline": build_guest_timeline(order),
        "expires_at": access.expires_at,
    }
