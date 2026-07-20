"""
通知サービス層 — Twilio SMS 送信
環境変数 TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_PHONE が設定されていれば
Twilio 経由で実送信する。未設定ならダミー送信（ログ + SmsLog 記録のみ）。

予約確認SMSの文面は、店舗の SmsTemplate（支払方法別）が有効なら優先して使用し、
未設定なら従来どおり下記の既定文言を使う。
"""
import logging
import os
from typing import Optional

from core.models import Order, SmsLog, SmsTemplate

logger = logging.getLogger(__name__)

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_PHONE = os.getenv("TWILIO_FROM_PHONE", "")


# ── low-level ─────────────────────────────────

def _format_to_e164(phone: str) -> str:
    """国内番号を E.164 形式に変換（0XX → +81XX）"""
    if phone.startswith("+"):
        return phone
    if phone.startswith("0"):
        return "+81" + phone[1:]
    return phone


def send_sms(
    to_phone: str,
    body: str,
    order: Optional[Order] = None,
    template_type: str = SmsLog.TemplateType.OTHER,
    created_by=None,
) -> SmsLog:
    """
    SMS 送信。Twilio 環境変数があれば実送信、なければダミー。
    成功/失敗/対象外いずれも SmsLog に記録する。
    """
    meta = _log_meta(order, template_type, created_by)

    if not to_phone or to_phone == "cast":
        logger.info("SMS skip (no valid phone) → %s", to_phone)
        return SmsLog.objects.create(
            to_phone=to_phone or "", body=body,
            status=SmsLog.Status.SKIPPED,
            provider=SmsLog.Provider.NONE,
            error_message="送信先電話番号が未設定のため送信していません",
            **meta,
        )

    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_PHONE:
        return _send_twilio(to_phone, body, meta)

    # ダミー送信
    logger.info("SMS dummy send → %s : %s", to_phone, body[:60])
    return SmsLog.objects.create(
        to_phone=to_phone, body=body,
        status=SmsLog.Status.SENT,
        provider=SmsLog.Provider.NONE,
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


def _send_twilio(to_phone: str, body: str, meta: dict) -> SmsLog:
    """Twilio API で SMS を送信。TWILIO_FROM_PHONE は取得済みの SMS 送信可能な Twilio 番号。"""
    try:
        from twilio.rest import Client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=body,
            from_=TWILIO_FROM_PHONE,
            to=_format_to_e164(to_phone),
        )
        logger.info("SMS sent via Twilio → %s sid=%s", to_phone, message.sid)
        return SmsLog.objects.create(
            to_phone=to_phone, body=body,
            status=SmsLog.Status.SENT,
            provider=SmsLog.Provider.TWILIO,
            provider_message_id=message.sid or "",
            **meta,
        )
    except Exception as e:
        logger.error("SMS send failed → %s : %s", to_phone, str(e))
        return SmsLog.objects.create(
            to_phone=to_phone, body=body,
            status=SmsLog.Status.FAILED,
            provider=SmsLog.Provider.TWILIO,
            error_message=str(e),
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


def build_template_context(order: Order) -> dict:
    """テンプレートの差し込み変数。SmsTemplate.PLACEHOLDERS と対応させること。"""
    return {
        "customer_name": order.customer.display_name or "",
        "date": f"{order.start:%Y-%m-%d}",
        "start_time": f"{order.start:%H:%M}",
        "end_time": f"{order.end:%H:%M}",
        "course_name": order.course_name or order.course.name,
        "cast_name": order.cast.name,
        "room_name": order.room.name if order.room else "",
        "payment_method": order.get_payment_method_display(),
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
        f"{_payment_method_note(payment_method)}\n"
        "ありがとうございます。"
    )


def _default_confirmation_body(order: Order) -> str:
    return (
        f"【Roomink】ご予約が確定しました。\n"
        f"日時: {order.start:%Y-%m-%d %H:%M}〜{order.end:%H:%M}\n"
        f"コース: {order.course.name}\n"
        f"担当: {order.cast.name}\n"
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
    return send_sms(
        to_phone=order.customer.phone,
        body=build_confirmation_body(order),
        order=order,
        template_type=SmsLog.TemplateType.RESERVATION_CONFIRMATION,
        created_by=created_by,
    )


def notify_cast_order(order: Order, created_by=None) -> SmsLog:
    """予約確定時にキャストへ通知"""
    body = (
        f"【Roomink】予約通知\n"
        f"日時: {order.start:%Y-%m-%d %H:%M}〜{order.end:%H:%M}\n"
        f"コース: {order.course.name}\n"
        f"ルーム: {order.room.name}"
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
    body = (
        f"【Roomink】ご予約がキャンセルされました。\n"
        f"日時: {order.start:%Y-%m-%d %H:%M}〜{order.end:%H:%M}\n"
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
