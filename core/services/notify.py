"""
通知サービス層 — SMS / LINE 差し替え前提
現時点ではダミー送信（SmsLog への記録のみ）。
将来 LINE / Twilio に差し替える際は send_sms() の中身だけ変えればよい。
"""
import logging
from typing import Optional

from core.models import Order, SmsLog

logger = logging.getLogger(__name__)


# ── low-level ─────────────────────────────────

def send_sms(to_phone: str, body: str, order: Optional[Order] = None) -> SmsLog:
    """
    SMS 送信（ダミー）。
    将来は Twilio / LINE API 呼び出しに差し替え。
    """
    # TODO: 実送信処理をここに書く
    logger.info("SMS dummy send → %s : %s", to_phone, body[:60])

    return SmsLog.objects.create(
        order=order,
        to_phone=to_phone,
        body=body,
        status=SmsLog.Status.SENT,
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
