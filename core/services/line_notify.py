"""
LINE Push message 送信サービス
Store 単位の line_channel_access_token を優先し、未設定なら環境変数にフォールバック。
"""
import logging
import os

import requests as http_requests

from core.models import LineNotificationLog

logger = logging.getLogger(__name__)

_GLOBAL_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")


def _resolve_token(store):
    """Store の token → グローバル env の順で解決"""
    if store and store.line_is_enabled and store.line_channel_access_token:
        return store.line_channel_access_token
    return _GLOBAL_TOKEN


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
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            json={
                "to": cast.line_user_id,
                "messages": [{"type": "text", "text": message}],
            },
            timeout=10,
        )
        if resp.status_code == 200:
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
