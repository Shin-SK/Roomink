import os

import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration


def _scrub_event(event, hint):
    """認証情報や入力本文を監視サービスへ送らない。"""
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)
        request.pop("cookies", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            for key in list(headers):
                if key.lower() in {"authorization", "cookie", "x-csrftoken"}:
                    headers.pop(key, None)
    return event


def initialize_sentry():
    """SENTRY_DSN が明示設定された環境だけでエラー監視を有効化する。"""
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return False

    sentry_sdk.init(
        dsn=dsn,
        integrations=[DjangoIntegration()],
        environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
        release=os.getenv("SENTRY_RELEASE") or os.getenv("HEROKU_SLUG_COMMIT") or None,
        send_default_pii=False,
        max_request_body_size="never",
        traces_sample_rate=0.0,
        before_send=_scrub_event,
    )
    return True
