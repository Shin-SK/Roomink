"""
LINE Push message 送信サービス
Store 単位の line_channel_access_token を優先し、未設定なら環境変数にフォールバック。
"""
import logging
import os
import uuid

import requests as http_requests
from django.db import transaction

from core.models import LineNotificationLog, ShiftAssignment, Store

logger = logging.getLogger(__name__)

_GLOBAL_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")


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
