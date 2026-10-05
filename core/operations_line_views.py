import base64
import hashlib
import hmac
import json
import time

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import OperationsCase, OperationsCaseMessage, OperationsLineContact, Store
from .services.operations_intake import (
    LINE_COPY,
    _slack_call,
    create_slack_case_thread,
    create_slack_registration_review,
    queue_codex_dispatch,
    send_line_push,
    send_line_reply,
)
from .services.support_assistant import redact_sensitive_text


def _valid_signature(request):
    secret = settings.OPERATIONS_LINE_CHANNEL_SECRET
    if not secret:
        return False
    expected = base64.b64encode(
        hmac.new(secret.encode("utf-8"), request.body, hashlib.sha256).digest()
    ).decode("utf-8")
    return hmac.compare_digest(request.headers.get("X-Line-Signature", ""), expected)


def _active_case_for(contact):
    return (
        OperationsCase.objects.filter(
            reporter=contact,
            status=OperationsCase.Status.TRIAGE,
        )
        .order_by("-updated_at")
        .first()
    )


def _slack_signature_is_valid(request):
    secret = settings.OPERATIONS_SLACK_SIGNING_SECRET
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")
    if not secret or not timestamp or not signature:
        return False
    try:
        if abs(time.time() - int(timestamp)) > 60 * 5:
            return False
    except ValueError:
        return False
    base = f"v0:{timestamp}:".encode("utf-8") + request.body
    expected = "v0=" + hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def _bridge_authorized(request):
    token = settings.OPERATIONS_CODEX_BRIDGE_TOKEN
    header = request.headers.get("Authorization", "")
    return bool(token and hmac.compare_digest(header, f"Bearer {token}"))


def _registration_modal(trigger_id, contact):
    stores = list(Store.objects.order_by("name")[:100])
    options = [
        {"text": {"type": "plain_text", "text": store.name[:75]}, "value": str(store.pk)}
        for store in stores
    ]
    return {
        "trigger_id": trigger_id,
        "view": {
            "type": "modal",
            "callback_id": "operations_line_registration_submit",
            "private_metadata": str(contact.pk),
            "title": {"type": "plain_text", "text": "運営LINEの登録"},
            "submit": {"type": "plain_text", "text": "承認する"},
            "close": {"type": "plain_text", "text": "閉じる"},
            "blocks": [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*申請内容*\n{contact.registration_text or '（本文なし）'}"},
                },
                {
                    "type": "input",
                    "block_id": "store",
                    "label": {"type": "plain_text", "text": "店舗"},
                    "element": {
                        "type": "static_select",
                        "action_id": "store_id",
                        "placeholder": {"type": "plain_text", "text": "対象店舗を選択"},
                        "options": options,
                    },
                },
                {
                    "type": "input",
                    "block_id": "name",
                    "label": {"type": "plain_text", "text": "ご担当者名"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "display_name",
                        "initial_value": contact.display_name[:150],
                    },
                },
            ],
        },
    }


def _update_registration_notification(contact):
    if not contact.registration_slack_thread_ts:
        return
    _slack_call("chat.update", {
        "channel": contact.registration_slack_channel_id,
        "ts": contact.registration_slack_thread_ts,
        "text": f"Roomink運営LINE：{contact.store.name} / {contact.display_name} を承認済み",
        "blocks": [{
            "type": "section",
            "text": {"type": "mrkdwn", "text": (
                "*Roomink運営LINE：利用登録完了*\n"
                f"店舗: {contact.store.name}\nご担当者: {contact.display_name}"
            )},
        }],
    })


@extend_schema(
    operation_id="operations_line_webhook",
    request=OpenApiTypes.OBJECT,
    responses=OpenApiTypes.OBJECT,
)
@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def operations_line_webhook(request):
    """Roomink運営LINE専用。店舗・キャスト用の既存webhookには混ぜない。"""
    if not settings.OPERATIONS_LINE_INTAKE_ENABLED:
        return Response({"detail": "Operations LINE intake is disabled"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    if not _valid_signature(request):
        return Response({"detail": "Invalid signature"}, status=status.HTTP_403_FORBIDDEN)

    try:
        events = json.loads(request.body.decode("utf-8")).get("events", [])
    except (UnicodeDecodeError, json.JSONDecodeError):
        return Response({"detail": "Invalid payload"}, status=status.HTTP_400_BAD_REQUEST)

    for event in events:
        source = event.get("source") or {}
        # 運営LINEは承認済みの個人トークだけ。グループに店舗LINEを混在させない。
        if source.get("type") != "user" or not source.get("userId"):
            continue
        line_user_id = source["userId"]
        event_type = event.get("type")

        if event_type == "follow":
            OperationsLineContact.objects.get_or_create(line_user_id=line_user_id)
            send_line_reply(event.get("replyToken", ""), LINE_COPY["registration_prompt"])
            continue

        if event_type == "unsend":
            message_id = str((event.get("unsend") or {}).get("messageId") or "")
            if message_id:
                OperationsCaseMessage.objects.filter(
                    line_message_id=message_id,
                    withdrawn_at__isnull=True,
                ).update(content="", withdrawn_at=timezone.now())
            continue

        if event_type != "message":
            continue
        message = event.get("message") or {}
        if message.get("type") != "text":
            continue
        contact, _ = OperationsLineContact.objects.get_or_create(line_user_id=line_user_id)
        if contact.status != OperationsLineContact.Status.ACTIVE or not contact.store_id:
            # 初回本文はSlackの承認者だけが確認する。以後の追送で通知を増やさない。
            if contact.status == OperationsLineContact.Status.PENDING and not contact.registration_requested_at:
                contact.registration_text = redact_sensitive_text(message.get("text") or "")[:1000]
                contact.registration_requested_at = timezone.now()
                contact.save(update_fields=[
                    "registration_text", "registration_requested_at", "updated_at",
                ])
                create_slack_registration_review(contact)
                send_line_reply(event.get("replyToken", ""), LINE_COPY["registration_pending"])
            elif contact.status == OperationsLineContact.Status.DISABLED:
                send_line_reply(
                    event.get("replyToken", ""),
                    "恐れ入ります。こちらのアカウントは現在ご利用いただけない状態です。"
                    "お手数ですが、Roomink運営までご確認をお願いいたします。",
                )
            else:
                # Slack側の一時障害で最初の通知に失敗しても、次の連絡で安全に再試行する。
                if not contact.registration_slack_thread_ts:
                    create_slack_registration_review(contact)
                send_line_reply(event.get("replyToken", ""), LINE_COPY["registration_pending"])
            continue

        event_id = str(event.get("webhookEventId") or "")
        if event_id and OperationsCaseMessage.objects.filter(line_event_id=event_id).exists():
            continue
        content = redact_sensitive_text(message.get("text") or "")
        if not content:
            continue
        case = _active_case_for(contact)
        if case is None:
            case = OperationsCase.objects.create(store=contact.store, reporter=contact)
        try:
            OperationsCaseMessage.objects.create(
                case=case,
                role=OperationsCaseMessage.Role.REPORTER,
                content=content,
                line_event_id=event_id or None,
                line_message_id=str(message.get("id") or ""),
            )
        except IntegrityError:
            continue
        contact.last_seen_at = timezone.now()
        contact.save(update_fields=["last_seen_at", "updated_at"])
        case.triage_requested_at = timezone.now()
        case.save(update_fields=["triage_requested_at", "updated_at"])
        send_line_reply(
            event.get("replyToken", ""),
            LINE_COPY["intake_received"],
        )

    return Response({"ok": True})


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def operations_slack_interactions(request):
    """Slackは通知専用。承認・開始だけを安全に待機列へ渡す。"""
    if not _slack_signature_is_valid(request):
        return Response({"detail": "Invalid Slack signature"}, status=status.HTTP_403_FORBIDDEN)
    try:
        payload = json.loads(request.data.get("payload", ""))
    except (AttributeError, TypeError, json.JSONDecodeError):
        return Response({"detail": "Invalid Slack payload"}, status=status.HTTP_400_BAD_REQUEST)

    if payload.get("type") == "block_actions":
        action = (payload.get("actions") or [{}])[0]
        action_id = action.get("action_id")
        if action_id == "operations_line_registration_review":
            try:
                contact = OperationsLineContact.objects.get(pk=int(action.get("value")))
            except (OperationsLineContact.DoesNotExist, TypeError, ValueError):
                return Response({"detail": "Unknown registration"}, status=status.HTTP_404_NOT_FOUND)
            result = _slack_call("views.open", _registration_modal(payload.get("trigger_id", ""), contact))
            if not result:
                return Response({"text": "登録確認画面を開けませんでした。"}, status=status.HTTP_502_BAD_GATEWAY)
            return Response({})

        if action_id == "operations_line_start_work":
            try:
                case = OperationsCase.objects.get(pk=int(action.get("value")))
            except (OperationsCase.DoesNotExist, TypeError, ValueError):
                return Response({"detail": "Unknown case"}, status=status.HTTP_404_NOT_FOUND)
            if not case.codex_thread_id:
                return Response({"text": "Codex案件タスクの準備中です。作成完了後に開始できます。"})
            queued = queue_codex_dispatch(case, OperationsCase.CodexDispatchAction.START_WORK)
            return Response({"text": "Codexへ修正開始を依頼しました。起動でき次第、LINEにもご案内します。" if queued else "この案件はすでに起動待ちです。"})

    if payload.get("type") == "view_submission" and payload.get("view", {}).get("callback_id") == "operations_line_registration_submit":
        view = payload["view"]
        values = view.get("state", {}).get("values", {})
        selected = values.get("store", {}).get("store_id", {}).get("selected_option") or {}
        name = values.get("name", {}).get("display_name", {}).get("value", "").strip()
        errors = {}
        try:
            store = Store.objects.get(pk=int(selected.get("value")))
        except (Store.DoesNotExist, TypeError, ValueError):
            errors["store"] = "対象店舗を選択してください。"
            store = None
        if not name:
            errors["name"] = "ご担当者名を入力してください。"
        if errors:
            return Response({"response_action": "errors", "errors": errors})
        try:
            contact = OperationsLineContact.objects.get(pk=int(view.get("private_metadata")))
        except (OperationsLineContact.DoesNotExist, TypeError, ValueError):
            return Response({"response_action": "clear"})
        contact.store = store
        contact.display_name = name[:255]
        contact.status = OperationsLineContact.Status.ACTIVE
        contact.approved_at = timezone.now()
        contact.save(update_fields=["store", "display_name", "status", "approved_at", "updated_at"])
        _update_registration_notification(contact)
        send_line_push(contact.line_user_id, LINE_COPY["registration_complete"])
        return Response({"response_action": "clear"})

    return Response({})


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def operations_codex_bridge_next(request):
    """ローカルMac上のbridgeが次の案件だけを引き取る。Codexを外部公開しない。"""
    if not _bridge_authorized(request):
        return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
    with transaction.atomic():
        case = (
            OperationsCase.objects.select_for_update()
            .filter(codex_dispatch_status=OperationsCase.CodexDispatchStatus.PENDING)
            .select_related("store", "reporter")
            .order_by("codex_dispatch_requested_at", "pk")
            .first()
        )
        if not case:
            return Response(status=status.HTTP_204_NO_CONTENT)
        case.codex_dispatch_status = OperationsCase.CodexDispatchStatus.CLAIMED
        case.codex_dispatch_claimed_at = timezone.now()
        case.save(update_fields=["codex_dispatch_status", "codex_dispatch_claimed_at", "updated_at"])
        return Response({
            "case_id": case.pk,
            "action": case.codex_dispatch_action,
            "store_name": case.store.name,
            "category": case.get_category_display(),
            "summary": case.summary,
            "missing_information": case.missing_information,
            "source": redact_sensitive_text("\n".join(
                message.content for message in case.messages.filter(
                    role=OperationsCaseMessage.Role.REPORTER, withdrawn_at__isnull=True,
                ).exclude(content="")
            ))[:6000],
            "codex_thread_id": case.codex_thread_id,
            "codex_thread_url": case.codex_thread_url,
            "codex_worktree_path": case.codex_worktree_path,
        })


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def operations_codex_bridge_complete(request, case_id):
    """bridgeの完了通知。成功するまでLINEへ作業開始とは伝えない。"""
    if not _bridge_authorized(request):
        return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
    try:
        case = OperationsCase.objects.select_related("reporter").get(pk=case_id)
    except OperationsCase.DoesNotExist:
        return Response({"detail": "Unknown case"}, status=status.HTTP_404_NOT_FOUND)
    if case.codex_dispatch_status != OperationsCase.CodexDispatchStatus.CLAIMED:
        return Response({"detail": "No claimed dispatch"}, status=status.HTTP_409_CONFLICT)
    data = request.data
    if not data.get("success"):
        case.codex_dispatch_status = OperationsCase.CodexDispatchStatus.FAILED
        case.codex_dispatch_error = str(data.get("error") or "Codex bridge failed")[:2000]
        case.save(update_fields=["codex_dispatch_status", "codex_dispatch_error", "updated_at"])
        return Response({"ok": True})

    if case.codex_dispatch_action == OperationsCase.CodexDispatchAction.CREATE_THREAD:
        thread_id = str(data.get("codex_thread_id") or "")
        thread_url = str(data.get("codex_thread_url") or "")
        if not thread_id or not thread_url:
            return Response({"detail": "Thread details are required"}, status=status.HTTP_400_BAD_REQUEST)
        case.codex_thread_id = thread_id[:100]
        case.codex_thread_url = thread_url[:500]
        case.codex_worktree_path = str(data.get("codex_worktree_path") or "")[:2000]
        case.codex_dispatch_status = OperationsCase.CodexDispatchStatus.SUCCEEDED
        case.codex_dispatch_error = ""
        case.save(update_fields=[
            "codex_thread_id", "codex_thread_url", "codex_worktree_path",
            "codex_dispatch_status", "codex_dispatch_error", "updated_at",
        ])
        create_slack_case_thread(case)
        return Response({"ok": True})

    if case.codex_dispatch_action == OperationsCase.CodexDispatchAction.START_WORK:
        case.status = OperationsCase.Status.IN_PROGRESS
        case.codex_dispatch_status = OperationsCase.CodexDispatchStatus.SUCCEEDED
        case.codex_dispatch_error = ""
        case.codex_started_at = timezone.now()
        case.save(update_fields=[
            "status", "codex_dispatch_status", "codex_dispatch_error", "codex_started_at", "updated_at",
        ])
        if case.reporter_id:
            send_line_push(case.reporter.line_user_id, LINE_COPY["work_started"])
        return Response({"ok": True})
    return Response({"detail": "Unsupported dispatch"}, status=status.HTTP_400_BAD_REQUEST)
