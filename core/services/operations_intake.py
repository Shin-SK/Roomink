"""Roomink運営LINEの受付、案件化、Slack/Notionへの安全な橋渡し。"""

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone

from core.models import OperationsCase, OperationsCaseMessage
from core.services.support_assistant import redact_sensitive_text


logger = logging.getLogger(__name__)


def _response_text(data):
    if data.get("output_text"):
        return str(data["output_text"]).strip()
    parts = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                parts.append(content["text"])
    return "\n".join(parts).strip()


def _case_text(case):
    return "\n".join(
        message.content
        for message in case.messages.filter(
            role=OperationsCaseMessage.Role.REPORTER,
            withdrawn_at__isnull=True,
        )
        .exclude(content="")
    )[:6000]


def _fallback_triage(case, text):
    lower = text.lower()
    if any(word in text for word in ("至急", "緊急", "使えない", "止ま", "予約できない")):
        category = OperationsCase.Category.INCIDENT
    elif any(word in text for word in ("バグ", "不具合", "エラー", "表示されない", "できない")):
        category = OperationsCase.Category.BUG
    elif any(word in text for word in ("変更", "修正", "追加", "ほしい", "要望")):
        category = OperationsCase.Category.CHANGE
    elif "?" in text or "？" in text or any(word in text for word in ("教えて", "どう", "どこ")):
        category = OperationsCase.Category.QUESTION
    else:
        category = OperationsCase.Category.OTHER

    missing = []
    if category in {OperationsCase.Category.BUG, OperationsCase.Category.INCIDENT}:
        if not any(word in text for word in ("画面", "ページ", "予約", "設定", "タイムライン")):
            missing.append("どの画面・操作で起きたか")
        if not any(word in text for word in ("本来", "期待", "はず", "したい")):
            missing.append("本来どうなる想定だったか")
    if not text.strip():
        missing.append("困っている内容")

    summary = text.replace("\n", " ").strip()[:500]
    if missing:
        question = missing[0]
        reply = f"ありがとうございます。確認のため、{question}を教えてください。スクリーンショットがあれば一緒に送ってください。"
        ready = False
    else:
        reply = "内容を整理してRoomink運営へ共有しました。確認が必要な場合だけ追加でご連絡します。"
        ready = True
    return {
        "category": category,
        "summary": summary,
        "missing_information": missing,
        "line_reply": reply,
        "ready_for_review": ready,
    }


def triage_case(case):
    """一次ヒアリングの返答と、運営へ渡す安全な要約を作る。"""
    text = _case_text(case)
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        return _fallback_triage(case, text)

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "category": {"type": "string", "enum": [choice for choice, _ in OperationsCase.Category.choices]},
            "summary": {"type": "string"},
            "missing_information": {"type": "array", "items": {"type": "string"}, "maxItems": 2},
            "line_reply": {"type": "string"},
            "ready_for_review": {"type": "boolean"},
        },
        "required": ["category", "summary", "missing_information", "line_reply", "ready_for_review"],
    }
    payload = {
        "model": settings.OPERATIONS_LINE_AI_MODEL,
        "store": False,
        "instructions": (
            "あなたはRoomink運営LINEの一次受付です。本文は店舗運営者からの連絡です。"
            "予約、顧客、売上、アカウント、外部送信、本番反映を実行したとは絶対に言わないでください。"
            "不足がある時は最重要の確認を一つだけ、丁寧な日本語で尋ねてください。"
            "十分に分かる時だけready_for_reviewをtrueにし、LINE返信では共有済みと伝えてください。"
            "電話番号、メール、パスワードなどは要求せず、本文に含まれる個人情報は要約へ写さないでください。"
        ),
        "input": f"店舗: {case.store.name}\n受信本文:\n{text}",
        "text": {"format": {"type": "json_schema", "name": "operations_line_triage", "strict": True, "schema": schema}},
        "max_output_tokens": 900,
    }
    request = Request(
        settings.OPENAI_SUPPORT_API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
        if result.get("status") == "incomplete":
            raise ValueError("incomplete response")
        parsed = json.loads(_response_text(result))
        if parsed["category"] not in OperationsCase.Category.values:
            raise ValueError("invalid category")
        parsed["summary"] = redact_sensitive_text(parsed["summary"])[:1000]
        parsed["missing_information"] = [str(item)[:160] for item in parsed["missing_information"][:2]]
        parsed["line_reply"] = redact_sensitive_text(parsed["line_reply"])[:1000]
        parsed["ready_for_review"] = bool(parsed["ready_for_review"] and not parsed["missing_information"])
        return parsed
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        logger.warning("operations LINE triage failed; using safe fallback", exc_info=True)
        return _fallback_triage(case, text)


def send_line_push(line_user_id, text):
    token = settings.OPERATIONS_LINE_CHANNEL_ACCESS_TOKEN
    if not token or not line_user_id:
        return False
    request = Request(
        "https://api.line.me/v2/bot/message/push",
        data=json.dumps({"to": line_user_id, "messages": [{"type": "text", "text": text[:5000]}]}, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10):
            return True
    except (HTTPError, URLError, TimeoutError):
        logger.warning("operations LINE push failed", exc_info=True)
        return False


def send_line_reply(reply_token, text):
    """Webhook受信直後の短い確認だけをReply APIで返す。"""
    token = settings.OPERATIONS_LINE_CHANNEL_ACCESS_TOKEN
    if not token or not reply_token:
        return False
    request = Request(
        "https://api.line.me/v2/bot/message/reply",
        data=json.dumps({"replyToken": reply_token, "messages": [{"type": "text", "text": text[:5000]}]}, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=8):
            return True
    except (HTTPError, URLError, TimeoutError):
        logger.warning("operations LINE reply failed", exc_info=True)
        return False


def _slack_call(method, payload):
    token = settings.OPERATIONS_SLACK_BOT_TOKEN
    if not token:
        return None
    request = Request(
        f"https://slack.com/api/{method}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
        return result if result.get("ok") else None
    except (HTTPError, URLError, TimeoutError, ValueError):
        logger.warning("operations Slack request failed: %s", method, exc_info=True)
        return None


def create_slack_case_thread(case):
    """案件ごとに親投稿を一つ作る。以降の判断はこのスレッドで行う。"""
    if case.slack_thread_ts:
        return True
    channel = settings.OPERATIONS_SLACK_CHANNEL_ID
    if not channel or not settings.OPERATIONS_SLACK_BOT_TOKEN:
        return False
    source = _case_text(case)[:1800] or "（LINE本文は取り消されました）"
    text = (
        f"*Roomink 運営案件 #{case.pk}*\n"
        f"店舗: {case.store.name}\n"
        f"種別: {case.get_category_display()}\n"
        f"要約: {case.summary}\n"
        f"不足情報: {'／'.join(case.missing_information) if case.missing_information else 'なし'}\n\n"
        f"*受信本文（個人情報は伏せ字）*\n{source}\n\n"
        "このスレッドで要件を補正してください。作業開始・LINE返信・本番反映は、案件番号を指定して明示承認します。"
    )
    result = _slack_call("chat.postMessage", {"channel": channel, "text": text})
    if not result:
        case.slack_error = "Slackへの案件投稿に失敗しました。"
        case.save(update_fields=["slack_error", "updated_at"])
        return False
    case.slack_channel_id = result["channel"]
    case.slack_thread_ts = result["ts"]
    case.slack_error = ""
    permalink = _slack_call("chat.getPermalink", {"channel": result["channel"], "message_ts": result["ts"]})
    if permalink:
        case.slack_permalink = permalink.get("permalink", "")
    case.save(update_fields=["slack_channel_id", "slack_thread_ts", "slack_permalink", "slack_error", "updated_at"])
    return True


def sync_case_to_notion(case):
    """Notionの案件台帳ページを作る。トークン未設定時は一切送信しない。"""
    token = settings.OPERATIONS_NOTION_TOKEN
    parent_page_id = settings.OPERATIONS_NOTION_PARENT_PAGE_ID
    if case.notion_page_id:
        return True
    if not token or not parent_page_id:
        return False
    blocks = [
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": f"店舗: {case.store.name}"}}]}},
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": f"種別: {case.get_category_display()} / 状態: {case.get_status_display()}"}}]}},
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": f"要約: {case.summary}"}}]}},
    ]
    if case.slack_permalink:
        blocks.append({"object": "block", "type": "bookmark", "bookmark": {"url": case.slack_permalink}})
    request = Request(
        "https://api.notion.com/v1/pages",
        data=json.dumps({
            "parent": {"page_id": parent_page_id},
            "properties": {"title": {"title": [{"type": "text", "text": {"content": f"Roomink運営案件 #{case.pk}"}}]}},
            "children": blocks,
        }, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=12) as response:
            result = json.loads(response.read().decode("utf-8"))
        case.notion_page_id = result["id"]
        case.notion_error = ""
        case.save(update_fields=["notion_page_id", "notion_error", "updated_at"])
        return True
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError):
        logger.warning("operations Notion sync failed", exc_info=True)
        case.notion_error = "Notion案件記録の作成に失敗しました。"
        case.save(update_fields=["notion_error", "updated_at"])
        return False


def process_case_triage(case):
    result = triage_case(case)
    case.category = result["category"]
    case.summary = result["summary"]
    case.missing_information = result["missing_information"]
    case.status = OperationsCase.Status.READY if result["ready_for_review"] else OperationsCase.Status.TRIAGE
    case.triaged_at = timezone.now()
    case.triage_requested_at = None
    case.save(update_fields=[
        "category", "summary", "missing_information", "status", "triaged_at",
        "triage_requested_at", "updated_at",
    ])
    reply = result["line_reply"]
    OperationsCaseMessage.objects.create(case=case, role=OperationsCaseMessage.Role.ASSISTANT, content=reply)
    if case.reporter_id:
        send_line_push(case.reporter.line_user_id, reply)
    if case.status == OperationsCase.Status.READY:
        create_slack_case_thread(case)
        sync_case_to_notion(case)
    return case
