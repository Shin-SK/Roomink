"""
通知サービス層 — Twilio SMS 送信
環境変数 TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_PHONE が設定されていれば
Twilio 経由で実送信する。未設定ならダミー送信（ログ + SmsLog 記録のみ）。
"""
import logging
import os
from typing import Optional

from core.models import Order, SmsLog

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


def send_sms(to_phone: str, body: str, order: Optional[Order] = None) -> SmsLog:
    """
    SMS 送信。Twilio 環境変数があれば実送信、なければダミー。
    成功/失敗いずれも SmsLog に記録する。
    """
    if not to_phone or to_phone == "cast":
        logger.info("SMS skip (no valid phone) → %s", to_phone)
        return SmsLog.objects.create(
            order=order, to_phone=to_phone or "", body=body,
            status=SmsLog.Status.SENT,
        )

    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_PHONE:
        return _send_twilio(to_phone, body, order)

    # ダミー送信
    logger.info("SMS dummy send → %s : %s", to_phone, body[:60])
    return SmsLog.objects.create(
        order=order, to_phone=to_phone, body=body,
        status=SmsLog.Status.SENT,
    )


def _send_twilio(to_phone: str, body: str, order: Optional[Order] = None) -> SmsLog:
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
            order=order, to_phone=to_phone, body=body,
            status=SmsLog.Status.SENT,
        )
    except Exception as e:
        logger.error("SMS send failed → %s : %s", to_phone, str(e))
        return SmsLog.objects.create(
            order=order, to_phone=to_phone, body=body,
            status=SmsLog.Status.FAILED,
        )


# ── high-level: 予約承認 ─────────────────────

def notify_order_confirmed(order: Order) -> SmsLog:
    """予約確定時に顧客へ通知"""
    body = (
        f"【Roomink】ご予約が確定しました。\n"
        f"日時: {order.start:%Y-%m-%d %H:%M}〜{order.end:%H:%M}\n"
        f"コース: {order.course.name}\n"
        f"担当: {order.cast.name}\n"
        f"ありがとうございます。"
    )
    return send_sms(
        to_phone=order.customer.phone,
        body=body,
        order=order,
    )


def notify_cast_order(order: Order) -> SmsLog:
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
    )


# ── high-level: 予約キャンセル ────────────────

def notify_order_cancelled(order: Order) -> SmsLog:
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
    )
