"""
LINE Push message 送信サービス
Store 単位の line_channel_access_token を優先し、未設定なら環境変数にフォールバック。
"""
import logging
import os
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests as http_requests
from django.db import transaction
from django.utils import timezone

from core.models import LineNotificationLog, Order, ShiftAssignment, Store

logger = logging.getLogger(__name__)

_GLOBAL_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
_WEEKDAYS_JA = ("月", "火", "水", "木", "金", "土", "日")


def _line_retry_key(shift_assignment, notification_type):
    """同じシフト通知の再送では、LINE に同一リトライキーを渡す。"""
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"roomink:line-notification:{shift_assignment.pk}:{notification_type}",
    ))


def _push_headers(token, shift_assignment, notification_type):
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "X-Line-Retry-Key": _line_retry_key(shift_assignment, notification_type),
    }


def _order_retry_key(order, notification_type):
    """同じ予約通知の再試行では、LINE に同一リトライキーを渡す。"""
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"roomink:line-order-notification:{order.pk}:{notification_type}",
    ))


def _order_push_headers(token, order, notification_type):
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "X-Line-Retry-Key": _order_retry_key(order, notification_type),
    }


def _line_accepted_response(response):
    """初回の200と、同一retry keyの受理済み409を送信成功として扱う。"""
    if response.status_code == 200:
        return True
    if response.status_code != 409:
        return False
    headers = getattr(response, "headers", {}) or {}
    return bool(headers.get("x-line-accepted-request-id"))


def _resolve_token(store):
    """Store の token → グローバル env の順で解決"""
    if not store or not store.line_is_operational:
        return ""
    return store.line_channel_access_token or _GLOBAL_TOKEN


def operations_push_is_configured(store):
    """運営通知の外部送信に必要な設定がすべて揃っているか返す。"""
    return bool(
        store
        and store.line_is_operational
        and store.line_shift_end_alert_enabled
        and store.line_operations_recipient_id
        and (store.line_channel_access_token or _GLOBAL_TOKEN)
    )


def send_line_push_once(store_id, shift_assignment_id, message, notification_type):
    """同じシフトの通常リマインダーを一度だけ送る。

    複数のSchedulerが同時に起動しても、店舗→シフトの順で行ロックを取得して
    「既に送信済みか」の確認と外部送信・ログ保存を直列化する。FAILEDは同じ
    retry keyで再試行できるが、SENT/SKIPPEDは再送しない。
    """
    with transaction.atomic():
        store = Store.objects.select_for_update().filter(pk=store_id).first()
        if store is None or not store.line_is_operational:
            return None
        shift = (
            ShiftAssignment.objects.select_for_update()
            .select_related("cast")
            .filter(pk=shift_assignment_id, store=store)
            .first()
        )
        if shift is None:
            return None
        if LineNotificationLog.objects.filter(
            shift_assignment=shift,
            notification_type=notification_type,
            status__in=(
                LineNotificationLog.Status.SENT,
                LineNotificationLog.Status.SKIPPED,
            ),
        ).exists():
            return None

        # select_related の古いStoreインスタンスを使わず、ロック済みの現在値で送る。
        shift.cast.store = store
        return send_line_push(
            shift.cast,
            message,
            shift,
            notification_type,
        )


def send_line_push(cast, message, shift_assignment, notification_type):
    """
    Cast に LINE Push message を送信し、LineNotificationLog を記録する。
    Returns: LineNotificationLog
    """
    store = cast.store
    token = _resolve_token(store)

    if not cast.line_user_id:
        logger.info("LINE push skip (unlinked): cast=%s type=%s", cast.name, notification_type)
        return LineNotificationLog.objects.create(
            store=store,
            cast=cast,
            shift_assignment=shift_assignment,
            notification_type=notification_type,
            status=LineNotificationLog.Status.SKIPPED,
            error_message="LINE未連携",
        )

    if not token:
        logger.info("LINE push dummy: cast=%s type=%s msg=%s", cast.name, notification_type, message[:40])
        return LineNotificationLog.objects.create(
            store=store,
            cast=cast,
            shift_assignment=shift_assignment,
            notification_type=notification_type,
            status=LineNotificationLog.Status.SENT,
            error_message="dummy (no token)",
        )

    try:
        resp = http_requests.post(
            "https://api.line.me/v2/bot/message/push",
            headers=_push_headers(token, shift_assignment, notification_type),
            json={
                "to": cast.line_user_id,
                "messages": [{"type": "text", "text": message}],
            },
            timeout=10,
        )
        if _line_accepted_response(resp):
            logger.info("LINE push sent: cast=%s type=%s", cast.name, notification_type)
            return LineNotificationLog.objects.create(
                store=store,
                cast=cast,
                shift_assignment=shift_assignment,
                notification_type=notification_type,
                status=LineNotificationLog.Status.SENT,
            )
        else:
            error_msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
            logger.error("LINE push failed: cast=%s type=%s error=%s", cast.name, notification_type, error_msg)
            return LineNotificationLog.objects.create(
                store=store,
                cast=cast,
                shift_assignment=shift_assignment,
                notification_type=notification_type,
                status=LineNotificationLog.Status.FAILED,
                error_message=error_msg,
            )
    except Exception as e:
        error_msg = str(e)[:500]
        logger.error("LINE push exception: cast=%s type=%s error=%s", cast.name, notification_type, error_msg)
        return LineNotificationLog.objects.create(
            store=store,
            cast=cast,
            shift_assignment=shift_assignment,
            notification_type=notification_type,
            status=LineNotificationLog.Status.FAILED,
            error_message=error_msg,
        )


def send_line_operations_push(
    store,
    cast,
    message,
    shift_assignment,
    notification_type,
):
    """登録済みの運営トークへ送信する。設定不足時は送信済みログを作らない。"""
    if not operations_push_is_configured(store):
        logger.warning(
            "LINE operations push skipped (configuration missing): store=%s type=%s",
            store.pk if store else None,
            notification_type,
        )
        return None

    token = store.line_channel_access_token or _GLOBAL_TOKEN
    try:
        resp = http_requests.post(
            "https://api.line.me/v2/bot/message/push",
            headers=_push_headers(token, shift_assignment, notification_type),
            json={
                "to": store.line_operations_recipient_id,
                "messages": [{"type": "text", "text": message}],
            },
            timeout=10,
        )
        if _line_accepted_response(resp):
            logger.info(
                "LINE operations push sent: store=%s cast=%s type=%s",
                store.pk,
                cast.pk,
                notification_type,
            )
            return LineNotificationLog.objects.create(
                store=store,
                cast=cast,
                shift_assignment=shift_assignment,
                notification_type=notification_type,
                status=LineNotificationLog.Status.SENT,
            )

        error_msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
        logger.error(
            "LINE operations push failed: store=%s cast=%s type=%s error=%s",
            store.pk,
            cast.pk,
            notification_type,
            error_msg,
        )
    except Exception as exc:
        error_msg = str(exc)[:500]
        logger.error(
            "LINE operations push exception: store=%s cast=%s type=%s error=%s",
            store.pk,
            cast.pk,
            notification_type,
            error_msg,
        )

    return LineNotificationLog.objects.create(
        store=store,
        cast=cast,
        shift_assignment=shift_assignment,
        notification_type=notification_type,
        status=LineNotificationLog.Status.FAILED,
        error_message=error_msg,
    )


def build_order_confirmation_message(order):
    """個人宛て予約通知。顧客の個人情報は本文に含めない。"""
    timezone_name = order.store.timezone or "Asia/Tokyo"
    try:
        store_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        store_timezone = timezone.get_default_timezone()
    start = timezone.localtime(order.start, store_timezone)
    end = timezone.localtime(order.end, store_timezone)
    weekday = _WEEKDAYS_JA[start.weekday()]
    return (
        "【Roomink】予約が確定しました\n"
        f"日時：{start:%Y/%m/%d（{weekday}）%H:%M}〜{end:%H:%M}\n"
        f"コース：{order.course_name or order.course.name}\n"
        f"ルーム：{order.room.name if order.room else '未定'}\n"
        "詳細はRoominkでご確認ください。"
    )


def send_order_confirmation_push_once(order_id):
    """予約確定を担当キャストへ一度だけ通知する。

    店舗のLINEが未開始なら外部送信もログ作成も行わない。未連携・失敗は
    予約確定を妨げず、運営が確認できる記録だけを残す。
    """
    notification_type = LineNotificationLog.NotificationType.ORDER_CONFIRMED
    with transaction.atomic():
        order = (
            Order.objects.select_for_update()
            .select_related("store", "cast", "room", "course")
            .filter(pk=order_id, status=Order.Status.CONFIRMED)
            .first()
        )
        if order is None or not order.store.line_is_operational:
            return None
        if LineNotificationLog.objects.filter(
            order=order,
            notification_type=notification_type,
            status__in=(
                LineNotificationLog.Status.SENT,
                LineNotificationLog.Status.SKIPPED,
            ),
        ).exists():
            return None

        message = build_order_confirmation_message(order)
        cast = order.cast
        if not cast.line_user_id:
            logger.info("LINE order notification skipped (unlinked): order=%s cast=%s", order.pk, cast.pk)
            return LineNotificationLog.objects.create(
                store=order.store,
                cast=cast,
                order=order,
                notification_type=notification_type,
                status=LineNotificationLog.Status.SKIPPED,
                message=message,
                error_message="LINE未連携",
            )

        token = _resolve_token(order.store)
        if not token:
            logger.error("LINE order notification failed (token missing): order=%s", order.pk)
            return LineNotificationLog.objects.create(
                store=order.store,
                cast=cast,
                order=order,
                notification_type=notification_type,
                status=LineNotificationLog.Status.FAILED,
                message=message,
                error_message="LINE送信設定が不足しています",
            )

        try:
            response = http_requests.post(
                "https://api.line.me/v2/bot/message/push",
                headers=_order_push_headers(token, order, notification_type),
                json={
                    "to": cast.line_user_id,
                    "messages": [{"type": "text", "text": message}],
                },
                timeout=10,
            )
            if _line_accepted_response(response):
                logger.info("LINE order notification sent: order=%s cast=%s", order.pk, cast.pk)
                return LineNotificationLog.objects.create(
                    store=order.store,
                    cast=cast,
                    order=order,
                    notification_type=notification_type,
                    status=LineNotificationLog.Status.SENT,
                    message=message,
                )
            error_message = f"HTTP {response.status_code}: {response.text[:200]}"
        except Exception as exc:
            error_message = str(exc)[:500]

        logger.error("LINE order notification failed: order=%s cast=%s error=%s", order.pk, cast.pk, error_message)
        return LineNotificationLog.objects.create(
            store=order.store,
            cast=cast,
            order=order,
            notification_type=notification_type,
            status=LineNotificationLog.Status.FAILED,
            message=message,
            error_message=error_message,
        )
