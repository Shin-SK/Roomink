import json
import logging
import re
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from django.utils.html import strip_tags

from core.models import CastNote


logger = logging.getLogger(__name__)


SUPPORT_KNOWLEDGE = [
    {
        "title": "カード決済後のSMS送信",
        "path": "/op/orders/{id}",
        "roles": {"manager", "staff"},
        "keywords": ("カード", "決済", "確認後", "sms", "住所", "送信"),
        "answer": "予約詳細画面を開き、カード決済の確認操作を行った後に「決済確認後SMSを送る」から2通目を送信できます。送信前に表示されるプレビューで、ルーム住所と案内文を確認してください。",
    },
    {
        "title": "SMSテンプレート設定",
        "path": "/op/settings/sms-templates",
        "roles": {"manager", "staff"},
        "keywords": ("sms", "文面", "テンプレート", "差し込み", "プレビュー"),
        "answer": "SMSの文面と差し込み項目は「設定 → SMS設定」で確認できます。プレビューは実送信を行わないため、番号取得前でも完成形を確認できます。",
    },
    {
        "title": "キャスト登録・編集",
        "path": "/op/settings/casts",
        "roles": {"manager"},
        "keywords": ("キャスト", "セラピスト", "登録", "画像", "雑費", "バック率", "希望エリア"),
        "answer": "キャストの登録・画像・雑費・給与率・希望エリアは「設定 → キャスト」から管理できます。既存キャストは一覧の編集ボタンから変更してください。",
    },
    {
        "title": "顧客管理",
        "path": "/op/customers",
        "roles": {"manager", "staff"},
        "keywords": ("顧客", "お客様", "電話番号", "履歴", "メモ", "出禁", "統合"),
        "answer": "顧客情報は「顧客管理」から検索・登録・編集できます。電話番号や利用履歴などの個人情報は、このサポート欄へ入力せず顧客詳細画面で扱ってください。",
    },
    {
        "title": "顧客CSV取込",
        "path": "/op/settings/csv-import",
        "roles": {"manager"},
        "keywords": ("csv", "取込", "インポート", "顧客データ", "雛形"),
        "answer": "顧客CSVは「設定 → CSV取込」で雛形をダウンロードし、最初にプレビューで内容を確認してから登録できます。エラー行がある場合は登録前に表示されます。",
    },
    {
        "title": "シフト・予約不可時間",
        "path": "/op/schedule",
        "roles": {"manager", "staff"},
        "keywords": ("シフト", "当欠", "休憩", "遅刻", "早退", "中抜け", "入れ替え", "予約不可"),
        "answer": "シフトと予約不可時間は予約タイムラインから対象キャストを選んで登録できます。当日欠勤の履歴はシフト管理側で「当欠」として処理してください。",
    },
    {
        "title": "ノート管理",
        "path": "/op/cast-notes",
        "roles": {"manager", "staff"},
        "keywords": ("ノート", "記事", "画像", "公開", "並び替え", "閲覧制限"),
        "answer": "ノートは「ノート」画面で作成・公開できます。本文中へ画像を挿入でき、一覧ではドラッグ操作で並び替えられます。公開範囲と対象キャストを必ず確認してください。",
    },
    {
        "title": "Web予約設定",
        "path": "/op/settings/public-booking",
        "roles": {"manager"},
        "keywords": ("web予約", "予約ページ", "注意事項", "公開url"),
        "answer": "Web予約の公開状態・注意事項・店舗専用URLは「設定 → Web予約設定」で確認できます。店舗専用URLを使うことで、他店舗を表示せず案内できます。",
    },
    {
        "title": "受付電話設定",
        "path": "/op/settings/phones",
        "roles": {"manager"},
        "keywords": ("電話", "cti", "sip", "groundwire", "qr", "着信", "受付端末"),
        "answer": "受付電話と受話端末は「設定 → 電話設定」で管理します。端末ごとの使い切り設定リンクを発行でき、退職・紛失時はその端末だけ無効化できます。",
    },
    {
        "title": "キャストの予約確認",
        "path": "/cast/orders",
        "roles": {"cast"},
        "keywords": ("予約", "タイムライン", "お客様", "今日", "予定"),
        "answer": "自分の予約は「タイムライン」から確認できます。表示内容に誤りがある場合は、予約を直接変更せず店舗スタッフへ確認してください。",
    },
    {
        "title": "キャストのシフト申請",
        "path": "/cast/shift-requests",
        "roles": {"cast"},
        "keywords": ("シフト", "申請", "希望", "提出", "複数日"),
        "answer": "シフト希望は「シフト申請」から複数日まとめて提出できます。承認前の申請は画面から確認してください。",
    },
    {
        "title": "お客様の予約確認",
        "path": "/s/{store_slug}/mypage",
        "roles": {"customer"},
        "keywords": ("予約", "確認", "日時", "キャスト", "住所", "マイページ"),
        "answer": "予約日時・担当キャスト・ルーム案内はマイページから確認できます。表示されない場合は、予約時と同じ店舗専用URLでログインしているか確認してください。",
    },
    {
        "title": "お客様の予約申込",
        "path": "/s/{store_slug}/mypage/booking",
        "roles": {"customer"},
        "keywords": ("予約", "申込", "空き", "コース", "キャスト"),
        "answer": "ログイン済みのお客様はマイページの「予約」から空き枠を選べます。確定済みの予約変更・キャンセルは店舗へお問い合わせください。",
    },
]


def redact_sensitive_text(value):
    text = str(value or "")[:2000]
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "<メールアドレス>", text)
    text = re.sub(r"(?<!\d)(?:\+?81[- ]?|0)\d{1,4}[- ]?\d{1,4}[- ]?\d{3,4}(?!\d)", "<電話番号>", text)
    text = re.sub(r"(?i)(password|パスワード)\s*[:：=]\s*\S+", r"\1: <非表示>", text)
    return text.strip()


def _score(item, question, page_path):
    haystack = f"{question} {page_path}".lower()
    score = sum(2 for word in item["keywords"] if word.lower() in haystack)
    concrete_path = item["path"].split("/{", 1)[0]
    if concrete_path and page_path.startswith(concrete_path):
        score += 5
    return score


def build_knowledge(store, user, role, question, page_path):
    candidates = [item for item in SUPPORT_KNOWLEDGE if role in item["roles"]]
    ranked = sorted(candidates, key=lambda item: _score(item, question, page_path), reverse=True)
    selected = [item for item in ranked if _score(item, question, page_path) > 0][:4]
    if not selected and ranked:
        selected = ranked[:2]

    entries = [
        {"title": item["title"], "path": item["path"], "content": item["answer"]}
        for item in selected
    ]

    note_filter = Q(visibility=CastNote.Visibility.ALL)
    if role in {"manager", "staff"}:
        note_filter |= Q(visibility=CastNote.Visibility.STAFF)
    elif role == "cast":
        note_filter |= Q(visibility=CastNote.Visibility.CAST)

    if role in {"manager", "staff", "cast"}:
        notes = CastNote.objects.filter(
            store=store,
            status=CastNote.Status.PUBLISHED,
        ).filter(note_filter)
        if role == "cast":
            cast = getattr(user, "cast_profile", None)
            if cast is None:
                notes = notes.none()
            else:
                notes = notes.filter(Q(target_casts__isnull=True) | Q(target_casts=cast)).distinct()
        question_terms = [
            term for term in re.split(r"[\s、。！？?とをにはがでのへ]+", question)
            if len(term) >= 2
        ]
        for note in notes.order_by("-is_pinned", "sort_order", "id")[:20]:
            body = re.sub(r"\s+", " ", strip_tags(note.body or "")).strip()
            note_text = f"{note.title} {body}"
            note_score = sum(1 for term in question_terms if term in note_text)
            if note_score:
                entries.append({
                    "title": f"店舗ノート: {note.title}",
                    "path": "/op/cast-notes" if role in {"manager", "staff"} else "/cast/mypage",
                    "content": body[:800],
                })

    return entries[:6]


def _fallback_answer(entries):
    if not entries:
        return "この質問に一致する案内を見つけられませんでした。「運営へ確認を依頼」を押すと、現在の画面情報と一緒に問い合わせを残せます。"
    return entries[0]["content"]


def _openai_answer(question, role, page_path, entries):
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        return None

    knowledge = "\n\n".join(
        f"[{entry['title']}]\n{entry['content']}\n画面: {entry['path']}"
        for entry in entries
    ) or "一致するマニュアルなし"
    payload = {
        "model": settings.OPENAI_SUPPORT_MODEL,
        "store": False,
        "instructions": (
            "あなたはRoominkの操作案内担当です。提示された根拠だけを使い、日本語で簡潔に答えてください。"
            "予約・売上・給与・アカウント・SMS・LINE等の変更や送信を実行したと表現してはいけません。"
            "個人情報やパスワードを求めてはいけません。不明な場合は推測せず、運営確認を案内してください。"
        ),
        "input": f"権限: {role}\n現在画面: {page_path}\n質問: {question}\n\n根拠:\n{knowledge}",
        "max_output_tokens": 500,
    }
    request = Request(
        settings.OPENAI_SUPPORT_API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError):
        logger.warning("Roomink support AI request failed", exc_info=True)
        return None

    if data.get("output_text"):
        return str(data["output_text"]).strip()
    parts = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                parts.append(content["text"])
    return "\n".join(parts).strip() or None


def answer_support_question(store, user, role, question, page_path):
    redacted = redact_sensitive_text(question)
    entries = build_knowledge(store, user, role, redacted, page_path)
    answer = _openai_answer(redacted, role, page_path, entries)
    return {
        "question": redacted,
        "answer": answer or _fallback_answer(entries),
        "sources": [{"title": entry["title"], "path": entry["path"]} for entry in entries[:4]],
        "mode": "ai" if answer else "fallback",
    }


def answer_support_followup(store, user, role, original_question, unresolved_reason, page_path):
    original = redact_sensitive_text(original_question)
    reason = redact_sensitive_text(unresolved_reason)
    combined = (
        f"最初の質問: {original}\n"
        f"前の案内で解決しなかった点: {reason}\n"
        "同じ説明の繰り返しではなく、別の確認方法または次に試す手順を案内してください。"
    )
    entries = build_knowledge(store, user, role, combined, page_path)
    ai_answer = _openai_answer(combined, role, page_path, entries)
    answer = ai_answer
    if not ai_answer:
        base = _fallback_answer(entries)
        answer = (
            "追加情報を確認しました。次の手順をもう一度ご確認ください。\n\n"
            f"{base}\n\n"
            "画面や表示内容が案内と異なる場合は、この下の「運営へ問い合わせる」から"
            "現在の状況を引き継げます。"
        )
    return {
        "reason": reason,
        "answer": answer,
        "sources": [{"title": entry["title"], "path": entry["path"]} for entry in entries[:4]],
        "mode": "ai" if ai_answer else "fallback",
    }


AUTO_REPLY_BLOCKED_KEYWORDS = (
    "契約", "料金", "請求", "返金", "解約", "パスワード", "ログインできない",
    "個人情報", "顧客情報", "削除", "変更して", "修正して", "不具合", "バグ",
    "売上", "給与", "振込", "権限", "アカウント発行",
)


def prepare_support_reply_draft(conversation):
    """問い合わせの返信案を作る。安全な操作案内だけ自動送信候補にする。"""
    latest = conversation.messages.filter(role="USER").order_by("-id").first()
    question = latest.content if latest else conversation.summary
    combined = f"{question}\n解決しなかった点: {conversation.unresolved_reason}".strip()
    result = answer_support_question(
        conversation.store,
        conversation.user,
        conversation.user_role,
        combined,
        conversation.page_path,
    )
    blocked = any(word in combined for word in AUTO_REPLY_BLOCKED_KEYWORDS)
    auto_send_allowed = bool(
        settings.SUPPORT_AUTO_REPLY_ENABLED
        and result["mode"] == "ai"
        and result["sources"]
        and not blocked
    )
    scheduled_at = None
    if auto_send_allowed:
        scheduled_at = timezone.now() + timedelta(
            minutes=max(5, settings.SUPPORT_AUTO_REPLY_DELAY_MINUTES),
        )
    return {
        "draft": result["answer"],
        "sources": result["sources"],
        "auto_send_allowed": auto_send_allowed,
        "scheduled_at": scheduled_at,
    }


def notify_support_slack(conversation):
    webhook_url = settings.SUPPORT_SLACK_WEBHOOK_URL
    if not webhook_url:
        return False
    latest = conversation.messages.filter(role="USER").order_by("-id").first()
    frontend_url = settings.FRONTEND_URL or ""
    detail_url = f"{frontend_url}/op/support?conversation={conversation.pk}" if frontend_url else ""
    heading = "Roomink 機能要望" if conversation.kind == "FEATURE" else "Roomink問い合わせ"
    message = (
        f"{heading} #{conversation.pk}\n"
        f"店舗: {conversation.store.name}\n権限: {conversation.user_role}\n"
        f"画面: {conversation.page_path or '-'}\n"
        f"内容: {(latest.content if latest else conversation.summary)[:600]}"
    )
    if detail_url:
        message += f"\n確認: {detail_url}"
    if conversation.ai_reply_draft:
        message += f"\n\nAI返信案:\n{conversation.ai_reply_draft[:800]}"
    if conversation.auto_reply_scheduled_at:
        local_time = timezone.localtime(conversation.auto_reply_scheduled_at)
        message += f"\n自動返信予定: {local_time:%Y-%m-%d %H:%M}（Roominkで停止できます）"
    request = Request(
        webhook_url,
        data=json.dumps({"text": message}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10):
            return True
    except (HTTPError, URLError, TimeoutError):
        logger.warning("Roomink support Slack notification failed", exc_info=True)
        return False


def notify_support_trend_slack(conversation, count):
    webhook_url = settings.SUPPORT_SLACK_WEBHOOK_URL
    if not webhook_url:
        return False
    frontend_url = settings.FRONTEND_URL or ""
    detail_url = f"{frontend_url}/op/support?conversation={conversation.pk}" if frontend_url else ""
    message = (
        "Roomink 回答改善候補\n"
        f"同じ画面・権限で未解決評価が直近14日間に{count}件あります。\n"
        f"店舗: {conversation.store.name}\n権限: {conversation.user_role}\n"
        f"画面: {conversation.page_path or '-'}"
    )
    if detail_url:
        message += f"\n確認: {detail_url}"
    request = Request(
        webhook_url,
        data=json.dumps({"text": message}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10):
            return True
    except (HTTPError, URLError, TimeoutError):
        logger.warning("Roomink support trend Slack notification failed", exc_info=True)
        return False
