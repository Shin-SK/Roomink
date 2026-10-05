"""Roomink運営LINEの受付、Codex案件化、Slack通知への安全な橋渡し。"""

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone

from core.models import OperationsCase, OperationsCaseMessage, OperationsLineContact
from core.services.support_assistant import redact_sensitive_text


logger = logging.getLogger(__name__)


LINE_COPY = {
    "registration_prompt": (
        "はじめまして。Roomink運営サポートです。\n"
        "お問い合わせありがとうございます！\n\n"
        "ご利用確認のため、まずは【店舗名】と【お名前】を"
        "お送りいただけますでしょうか。\n"
        "確認ができ次第、こちらでご相談を承ります。"
    ),
    "registration_pending": (
        "ありがとうございます！\n"
        "ただいま運営側でご利用確認をしております。\n"
        "確認が取れ次第、こちらからご案内いたしますので、少々お待ちください。"
    ),
    "registration_complete": (
        "お待たせいたしました。ご利用登録が完了しました！\n\n"
        "変更したいことやお困りごとがございましたら、こちらにそのままお送りください。\n"
        "スクリーンショットも添えていただけると、よりスムーズに確認できます。"
    ),
    "intake_received": (
        "ご連絡ありがとうございます。内容を確認しております。\n"
        "必要な点だけ、こちらからお伺いします。"
    ),
    "work_started": (
        "ご連絡ありがとうございます。内容を確認し、対応を進めることになりました。\n"
        "確認用の画面をご用意でき次第、こちらからお知らせいたします。"
    ),
}


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
        reply = (
            "ご連絡ありがとうございます。確認のため、"
            f"{question}を教えていただけますでしょうか。\n"
            "スクリーンショットがある場合は、あわせてお送りいただけると助かります。"
        )
        ready = False
    else:
        reply = (
            "ご回答ありがとうございます。内容を整理し、運営側へ共有いたしました。\n"
            "対応方針を確認のうえ、こちらからご連絡いたしますので、少々お待ちください。"
        )
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
            "不足がある時は最重要の確認を一つだけ、やわらかく丁寧な敬語で尋ねてください。"
            "相手を急かしたり、幼く扱ったり、くだけすぎたりしないでください。"
            "十分に分かる時だけready_for_reviewをtrueにし、LINE返信では運営側へ共有済みであることと、"
            "対応方針を確認して改めて連絡することを丁寧に伝えてください。"
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


def _slack_blocks(*, title, body, actions=None):
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": title[:150]}},
        {"type": "section", "text": {"type": "mrkdwn", "text": body[:2900]}},
    ]
    if actions:
        blocks.append({"type": "actions", "elements": actions})
    return blocks


def create_slack_registration_review(contact):
    """未承認の運営者をSlack上で確認するための通知を一度だけ送る。"""
    if contact.registration_slack_thread_ts:
        return True
    channel = settings.OPERATIONS_SLACK_CHANNEL_ID
    if not channel or not settings.OPERATIONS_SLACK_BOT_TOKEN:
        return False
    body = (
        "運営LINEの利用登録申請です。\n"
        f"申請内容: {contact.registration_text or '（本文なし）'}\n\n"
        "内容を確認し、店舗とお名前を指定して承認してください。"
    )
    result = _slack_call("chat.postMessage", {
        "channel": channel,
        "text": "Roomink運営LINE：利用登録申請",
        "blocks": _slack_blocks(
            title="Roomink運営LINE：利用登録申請",
            body=body,
            actions=[{
                "type": "button",
                "text": {"type": "plain_text", "text": "登録内容を確認"},
                "action_id": "operations_line_registration_review",
                "value": str(contact.pk),
            }],
        ),
    })
    if not result:
        return False
    contact.registration_slack_channel_id = result["channel"]
    contact.registration_slack_thread_ts = result["ts"]
    contact.save(update_fields=[
        "registration_slack_channel_id", "registration_slack_thread_ts", "updated_at",
    ])
    return True


def queue_codex_dispatch(case, action):
    """ローカルのCodex bridgeが取得する仕事を一件だけ待機列へ置く。"""
    if (
        case.codex_dispatch_action == action
        and case.codex_dispatch_status in {
            OperationsCase.CodexDispatchStatus.PENDING,
            OperationsCase.CodexDispatchStatus.CLAIMED,
        }
    ):
        return False
    case.codex_dispatch_action = action
    case.codex_dispatch_status = OperationsCase.CodexDispatchStatus.PENDING
    case.codex_dispatch_error = ""
    case.codex_dispatch_requested_at = timezone.now()
    case.codex_dispatch_claimed_at = None
    case.save(update_fields=[
        "codex_dispatch_action", "codex_dispatch_status", "codex_dispatch_error",
        "codex_dispatch_requested_at", "codex_dispatch_claimed_at", "updated_at",
    ])
    return True


def create_slack_case_thread(case):
    """実在するCodex案件タスクへの通知を、Slackに一度だけ作る。"""
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
        "詳細の確認・会話・作業は、Codexの案件タスクで行います。\n"
        "Slackは通知と、すぐ着手できる案件の開始操作だけに使います。"
    )
    actions = [{
        "type": "button",
        "text": {"type": "plain_text", "text": "Codexで案件を開く"},
        "url": case.codex_thread_url,
        "action_id": "operations_line_open_codex",
    }]
    actions.append({
        "type": "button",
        "text": {"type": "plain_text", "text": "修正開始"},
        "style": "primary",
        "action_id": "operations_line_start_work",
        "value": str(case.pk),
        "confirm": {
            "title": {"type": "plain_text", "text": "修正を開始しますか？"},
            "text": {"type": "mrkdwn", "text": "Codexの案件タスクで修正作業を開始します。"},
            "confirm": {"type": "plain_text", "text": "修正開始"},
            "deny": {"type": "plain_text", "text": "キャンセル"},
        },
    })
    result = _slack_call("chat.postMessage", {
        "channel": channel,
        "text": text,
        "blocks": _slack_blocks(title=f"Roomink運営案件 #{case.pk}", body=text, actions=actions),
    })
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
        # Codexの案件タスクが実在する前に、Slackから「開始」できるようにはしない。
        queue_codex_dispatch(case, OperationsCase.CodexDispatchAction.CREATE_THREAD)
    return case
