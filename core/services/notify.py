"""
通知サービス層 — Twilio SMS 送信
環境変数 TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_PHONE が設定されていれば
Twilio 経由で実送信する。未設定時は明示的な SMS_DUMMY_MODE の場合だけダミー記録する。

予約確認SMSの文面は、店舗の SmsTemplate（支払方法別）が有効なら優先して使用し、
未設定なら従来どおり下記の既定文言を使う。
"""
import logging
import os
from typing import Optional
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.utils import timezone

from core.models import Order, SmsLog, SmsTemplate

logger = logging.getLogger(__name__)

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_PHONE = os.getenv("TWILIO_FROM_PHONE", "")


# ── low-level ─────────────────────────────────

def _mask_phone(phone: str) -> str:
    digits = "".join(char for char in str(phone or "") if char.isdigit())
    return f"***{digits[-4:]}" if digits else "***"

def _format_to_e164(phone: str) -> str:
    """国内番号を E.164 形式に変換（0XX → +81XX）"""
    if phone.startswith("+"):
        return phone
    if phone.startswith("0"):
        return "+81" + phone[1:]
    return phone


def _local_order_datetimes(order: Order):
    """予約日時を店舗タイムゾーンへ変換する。"""
    timezone_name = order.store.timezone or settings.TIME_ZONE
    try:
        store_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        logger.warning(
            "Invalid store timezone; using Django default → store=%s timezone=%s",
            order.store_id,
            timezone_name,
        )
        store_timezone = timezone.get_default_timezone()
    return (
        timezone.localtime(order.start, store_timezone),
        timezone.localtime(order.end, store_timezone),
    )


def send_sms(
    to_phone: str,
    body: str,
    order: Optional[Order] = None,
    template_type: str = SmsLog.TemplateType.OTHER,
    created_by=None,
    log_body: Optional[str] = None,
) -> SmsLog:
    """
    SMS 送信。Twilio 環境変数があれば実送信する。
    log_body を指定した場合、機密URLを含む実送信本文の代わりに安全な本文を保存する。
    成功/失敗/対象外いずれも SmsLog に記録する。
    """
    meta = _log_meta(order, template_type, created_by)
    persisted_body = log_body if log_body is not None else body

    if not to_phone or to_phone == "cast":
        logger.info("SMS skip (no valid phone) → %s", _mask_phone(to_phone))
        return SmsLog.objects.create(
            to_phone=to_phone or "", body=persisted_body,
            status=SmsLog.Status.SKIPPED,
            provider=SmsLog.Provider.NONE,
            error_message="送信先電話番号が未設定のため送信していません",
            **meta,
        )

    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_PHONE:
        return _send_twilio(to_phone, body, persisted_body, meta)

    if settings.SMS_DUMMY_MODE:
        logger.info("SMS development dummy → %s", _mask_phone(to_phone))
        send_status = SmsLog.Status.DUMMY
        error_message = "DEVELOPMENT_DUMMY"
    else:
        logger.warning("SMS not sent (configuration missing) → %s", _mask_phone(to_phone))
        send_status = SmsLog.Status.CONFIG_MISSING
        error_message = "SMS_CONFIG_MISSING"
    return SmsLog.objects.create(
        to_phone=to_phone, body=persisted_body,
        status=send_status,
        provider=SmsLog.Provider.NONE,
        error_message=error_message,
        **meta,
    )


def _log_meta(order: Optional[Order], template_type: str, created_by) -> dict:
    """SmsLog に共通で載せる付帯情報を組み立てる。"""
    return {
        "order": order,
        "store": order.store if order else None,
        "customer": order.customer if order else None,
        "payment_method": order.payment_method if order else "",
        "template_type": template_type,
        "created_by": created_by if (created_by and created_by.is_authenticated) else None,
    }


def _send_twilio(to_phone: str, body: str, persisted_body: str, meta: dict) -> SmsLog:
    """Twilio API で SMS を送信。TWILIO_FROM_PHONE は取得済みの SMS 送信可能な Twilio 番号。"""
    try:
        from twilio.rest import Client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=body,
            from_=TWILIO_FROM_PHONE,
            to=_format_to_e164(to_phone),
        )
        logger.info("SMS sent via Twilio → %s sid=%s", _mask_phone(to_phone), message.sid)
        return SmsLog.objects.create(
            to_phone=to_phone, body=persisted_body,
            status=SmsLog.Status.SENT,
            provider=SmsLog.Provider.TWILIO,
            provider_message_id=message.sid or "",
            **meta,
        )
    except Exception as e:
        safe_error = str(e).replace(str(to_phone), _mask_phone(to_phone))
        logger.error("SMS send failed → %s : %s", _mask_phone(to_phone), safe_error)
        return SmsLog.objects.create(
            to_phone=to_phone, body=persisted_body,
            status=SmsLog.Status.FAILED,
            provider=SmsLog.Provider.TWILIO,
            error_message=safe_error,
            **meta,
        )


# ── 文面テンプレート ──────────────────────────

def _payment_method_note(payment_method: str) -> str:
    """決済方法に応じたSMS末尾の一文（テンプレート未設定時の既定文言）"""
    if payment_method == Order.PaymentMethod.CASH:
        return "当日は現金でのお支払いをお願いいたします。"
    if payment_method == Order.PaymentMethod.CARD:
        return "当日はカード決済でのご案内となります（手数料10%が発生します）。"
    if payment_method == Order.PaymentMethod.PAYPAY:
        return "当日はPayPay決済でのご案内となります（手数料5%が発生します）。"
    return "支払い方法については当日スタッフよりご案内いたします。"


def _room_guidance(order: Order) -> str:
    """予約に確定したルームの顧客向け案内。未定時は住所等を出さない。"""
    if not order.room:
        return "ルーム: 調整中"

    room = order.room
    lines = [f"ルーム: {room.name}"]
    if room.address:
        lines.append(f"住所: {room.address}")
    if room.map_url:
        lines.append(f"地図: {room.map_url}")
    if room.sms_notice:
        lines.append(f"※{room.sms_notice}")
    return "\n".join(lines)


def build_template_context(order: Order) -> dict:
    """テンプレートの差し込み変数。SmsTemplate.PLACEHOLDERS と対応させること。"""
    start, end = _local_order_datetimes(order)
    subtotal_price = order.total_price + order.discount_amount
    return {
        "customer_name": order.customer.display_name or "",
        "date": f"{start:%Y-%m-%d}",
        "start_time": f"{start:%H:%M}",
        "end_time": f"{end:%H:%M}",
        "course_name": order.course_name or order.course.name,
        "cast_name": order.cast.name,
        "room_name": order.room.name if order.room else "",
        "room_address": order.room.address if order.room else "",
        "room_map_url": order.room.map_url if order.room else "",
        "room_notice": order.room.sms_notice if order.room else "",
        "room_guidance": _room_guidance(order),
        "payment_method": order.get_payment_method_display(),
        "discount_name": order.discount_name or "",
        "discount_amount": f"{order.discount_amount:,}",
        "subtotal_price": f"{subtotal_price:,}",
        "total_price": f"{order.total_price:,}",
    }


def render_template(body: str, context: dict) -> str:
    """{placeholder} を差し込む。未知の変数が入っていても送信を止めない。"""
    class _SafeDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"

    try:
        return body.format_map(_SafeDict(context))
    except (ValueError, IndexError) as e:
        # 波括弧の対応が壊れている等。テンプレートをそのまま送るより既定文言に倒す。
        logger.warning("SMS template render failed: %s", e)
        return ""


def default_confirmation_preview(payment_method: str) -> str:
    """テンプレート未設定時に送信される既定文言（設定画面のプレビュー用）。"""
    return (
        "【Roomink】ご予約が確定しました。\n"
        "日時: {date} {start_time}〜{end_time}\n"
        "コース: {course_name}\n"
        "担当: {cast_name}\n"
        "{room_guidance}\n"
        f"{_payment_method_note(payment_method)}\n"
        "ありがとうございます。"
    )


def _default_confirmation_body(order: Order) -> str:
    start, end = _local_order_datetimes(order)
    return (
        f"【Roomink】ご予約が確定しました。\n"
        f"日時: {start:%Y-%m-%d %H:%M}〜{end:%H:%M}\n"
        f"コース: {order.course.name}\n"
        f"担当: {order.cast.name}\n"
        f"{_room_guidance(order)}\n"
        f"{_payment_method_note(order.payment_method)}\n"
        f"ありがとうございます。"
    )


def build_confirmation_body(order: Order) -> str:
    """予約確認SMSの本文。店舗テンプレートが有効ならそれを、無ければ既定文言を返す。"""
    tpl = (
        SmsTemplate.objects
        .filter(
            store=order.store,
            template_type=SmsTemplate.TemplateType.RESERVATION_CONFIRMATION,
            payment_method=order.payment_method or Order.PaymentMethod.UNSET,
            is_active=True,
        )
        .first()
    )
    if tpl and tpl.body.strip():
        rendered = render_template(tpl.body, build_template_context(order))
        if rendered.strip():
            return rendered
    return _default_confirmation_body(order)


# ── high-level: 予約承認 ─────────────────────

def notify_order_confirmed(order: Order, created_by=None) -> SmsLog:
    """予約確定時に顧客へ通知"""
    return notify_customer_account(order.customer, order=order, created_by=created_by)


def notify_customer_account(customer, order=None, created_by=None, force=False) -> SmsLog:
    """顧客の登録状態に応じ、初回設定URLまたはログインURLを予約案内へ付加する。"""
    from core.services.customer_invitation import issue_customer_invitation

    base_body = build_confirmation_body(order) if order else "【Roomink】お客様アカウントのご案内です。"
    frontend_url = settings.FRONTEND_URL
    if not frontend_url:
        logger.warning("Customer account SMS not sent (FRONTEND_URL missing) → %s", _mask_phone(customer.phone))
        return SmsLog.objects.create(
            to_phone=customer.phone,
            body="【Roomink】顧客案内（URL設定不足のため未送信）",
            status=SmsLog.Status.CONFIG_MISSING,
            provider=SmsLog.Provider.NONE,
            error_message="FRONTEND_URL_MISSING",
            **_log_meta(order, SmsLog.TemplateType.RESERVATION_CONFIRMATION, created_by),
        )

    invitation = None
    if customer.user_id:
        next_path = f"/cu/reservations/{order.id}?store={customer.store_id}" if order else f"/cu/mypage?store={customer.store_id}"
        customer_url = f"{frontend_url}/cu/login?{urlencode({'next': next_path})}"
        guidance = "予約内容は次のURLから確認できます。"
    else:
        invitation, raw_token = issue_customer_invitation(
            customer,
            order=order,
            created_by=created_by,
            force=force,
        )
        if raw_token:
            customer_url = f"{frontend_url}/cu/activate?{urlencode({'token': raw_token})}"
            guidance = "次のURLから72時間以内にパスワードを設定してください。"
        else:
            customer_url = f"{frontend_url}/cu/signup"
            guidance = "すでに初回設定のご案内を送信済みです。案内が見つからない場合は店舗へお問い合わせください。"

    body = f"{base_body}\n{guidance}\n{customer_url}"
    safe_body = f"{base_body}\n{guidance}\n[顧客用リンク]"
    sms_log = send_sms(
        to_phone=customer.phone,
        body=body,
        order=order,
        template_type=SmsLog.TemplateType.RESERVATION_CONFIRMATION,
        created_by=created_by,
        log_body=safe_body,
    )
    if invitation and invitation.sms_log_id is None:
        invitation.sms_log = sms_log
        invitation.save(update_fields=["sms_log"])
    return sms_log


def notify_cast_order(order: Order, created_by=None) -> SmsLog:
    """予約確定時にキャストへ通知"""
    start, end = _local_order_datetimes(order)
    body = (
        f"【Roomink】予約通知\n"
        f"日時: {start:%Y-%m-%d %H:%M}〜{end:%H:%M}\n"
        f"コース: {order.course.name}\n"
        f"ルーム: {order.room.name if order.room else '未定'}"
    )
    # キャストに電話番号がないため、仮に空文字で記録
    return send_sms(
        to_phone="cast",
        body=body,
        order=order,
        template_type=SmsLog.TemplateType.CAST_NOTICE,
        created_by=created_by,
    )


# ── high-level: 予約キャンセル ────────────────

def notify_order_cancelled(order: Order, created_by=None) -> SmsLog:
    """予約キャンセル時に顧客へ通知"""
    start, end = _local_order_datetimes(order)
    body = (
        f"【Roomink】ご予約がキャンセルされました。\n"
        f"日時: {start:%Y-%m-%d %H:%M}〜{end:%H:%M}\n"
        f"コース: {order.course.name}\n"
        f"ご不明点がございましたらお問い合わせください。"
    )
    return send_sms(
        to_phone=order.customer.phone,
        body=body,
        order=order,
        template_type=SmsLog.TemplateType.RESERVATION_CANCELLED,
        created_by=created_by,
    )
