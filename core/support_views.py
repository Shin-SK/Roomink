from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema

from .models import Customer, SupportConversation, SupportMessage, UserProfile
from .permissions import IsManager
from .services.support_assistant import (
    answer_support_followup,
    answer_support_question,
    notify_support_slack,
    notify_support_trend_slack,
    prepare_support_reply_draft,
    redact_sensitive_text,
)


def _support_context(request):
    profile = getattr(request.user, "profile", None)
    if profile is not None:
        return profile.store, profile.role

    store_slug = (request.data.get("store_slug") or request.query_params.get("store_slug") or "").strip()
    customers = Customer.objects.filter(user=request.user).select_related("store")
    if store_slug:
        customer = customers.filter(store__slug=store_slug).first()
        if customer is None:
            return None, None
    else:
        customer = customers.order_by("id").first()
    if customer is None:
        return None, None
    return customer.store, "customer"


def _serialize_message(message):
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "sources": message.sources,
        "created_at": message.created_at,
    }


def _serialize_conversation(conversation, include_messages=False):
    latest = conversation.messages.filter(role=SupportMessage.Role.USER).order_by("-id").first()
    data = {
        "id": conversation.id,
        "store_id": conversation.store_id,
        "store_name": conversation.store.name,
        "user_role": conversation.user_role,
        "page_path": conversation.page_path,
        "page_title": conversation.page_title,
        "kind": conversation.kind,
        "status": conversation.status,
        "summary": conversation.summary,
        "unresolved_reason": conversation.unresolved_reason,
        "unresolved_at": conversation.unresolved_at,
        "inquiry_submitted_at": conversation.inquiry_submitted_at,
        "ai_reply_draft": conversation.ai_reply_draft,
        "auto_reply_scheduled_at": conversation.auto_reply_scheduled_at,
        "auto_reply_sent_at": conversation.auto_reply_sent_at,
        "auto_reply_cancelled_at": conversation.auto_reply_cancelled_at,
        "has_unread_reply": bool(
            conversation.inquiry_submitted_at
            and conversation.messages.filter(
                role__in=[SupportMessage.Role.ASSISTANT, SupportMessage.Role.OPERATOR],
                created_at__gt=conversation.user_last_viewed_at or conversation.inquiry_submitted_at,
            ).exists()
        ),
        "latest_message": latest.content if latest else "",
        "slack_notified": conversation.slack_notified_at is not None,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }
    if include_messages:
        data["messages"] = [_serialize_message(message) for message in conversation.messages.all()]
    return data


def _accessible_conversation(request, conversation_id):
    conversation = get_object_or_404(
        SupportConversation.objects.select_related("store", "user"),
        pk=conversation_id,
    )
    if conversation.user_id == request.user.id:
        return conversation
    profile = getattr(request.user, "profile", None)
    if (
        profile is not None
        and profile.role == UserProfile.Role.MANAGER
        and profile.store_id == conversation.store_id
    ):
        return conversation
    return None


class SupportChatView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="support_chat_create",
        request=OpenApiTypes.OBJECT,
        responses=OpenApiTypes.OBJECT,
    )
    def post(self, request):
        store, role = _support_context(request)
        if store is None:
            return Response(
                {"detail": "この店舗のサポートを利用する権限がありません。"},
                status=status.HTTP_403_FORBIDDEN,
            )

        message = str(request.data.get("message") or "").strip()
        if not message:
            return Response({"detail": "質問を入力してください。"}, status=status.HTTP_400_BAD_REQUEST)
        if len(message) > 2000:
            return Response({"detail": "質問は2000文字以内で入力してください。"}, status=status.HTTP_400_BAD_REQUEST)

        recent_count = SupportMessage.objects.filter(
            conversation__user=request.user,
            role=SupportMessage.Role.USER,
            created_at__gte=timezone.now() - timedelta(hours=1),
        ).count()
        if recent_count >= 30:
            return Response(
                {"detail": "短時間の質問数が上限に達しました。しばらくしてからお試しください。"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        conversation_id = request.data.get("conversation_id")
        if conversation_id:
            conversation = _accessible_conversation(request, conversation_id)
            if (
                conversation is None
                or conversation.user_id != request.user.id
                or conversation.store_id != store.id
                or conversation.kind != SupportConversation.Kind.SUPPORT
            ):
                return Response({"detail": "会話が見つかりません。"}, status=status.HTTP_404_NOT_FOUND)
        else:
            conversation = SupportConversation.objects.create(
                store=store,
                user=request.user,
                user_role=role,
                page_path=str(request.data.get("page_path") or "")[:500],
                page_title=str(request.data.get("page_title") or "")[:200],
            )

        result = answer_support_question(
            store,
            request.user,
            role,
            message,
            conversation.page_path,
        )
        SupportMessage.objects.create(
            conversation=conversation,
            role=SupportMessage.Role.USER,
            content=result["question"],
        )
        assistant_message = SupportMessage.objects.create(
            conversation=conversation,
            role=SupportMessage.Role.ASSISTANT,
            content=result["answer"],
            sources=result["sources"],
        )
        conversation.status = SupportConversation.Status.OPEN
        conversation.save(update_fields=["status", "updated_at"])

        return Response({
            "conversation_id": conversation.id,
            "answer": assistant_message.content,
            "sources": assistant_message.sources,
            "mode": result["mode"],
        })


class SupportConversationResolveView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="support_conversation_resolve",
        request=OpenApiTypes.OBJECT,
        responses=OpenApiTypes.OBJECT,
    )
    def post(self, request, conversation_id):
        conversation = _accessible_conversation(request, conversation_id)
        if conversation is None:
            return Response({"detail": "会話が見つかりません。"}, status=status.HTTP_404_NOT_FOUND)
        conversation.status = SupportConversation.Status.RESOLVED
        conversation.resolved_at = timezone.now()
        conversation.save(update_fields=["status", "resolved_at", "updated_at"])
        return Response({"ok": True, "status": conversation.status})


class SupportConversationUnresolvedView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="support_conversation_unresolved",
        request=OpenApiTypes.OBJECT,
        responses=OpenApiTypes.OBJECT,
    )
    def post(self, request, conversation_id):
        conversation = _accessible_conversation(request, conversation_id)
        if conversation is None or conversation.user_id != request.user.id:
            return Response({"detail": "会話が見つかりません。"}, status=status.HTTP_404_NOT_FOUND)
        if conversation.kind != SupportConversation.Kind.SUPPORT:
            return Response({"detail": "この受付では追加案内を利用できません。"}, status=status.HTTP_400_BAD_REQUEST)
        reason = redact_sensitive_text(request.data.get("reason") or "")
        if len(reason) < 5:
            return Response(
                {"detail": "解決しなかった点を5文字以上で入力してください。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if conversation.unresolved_reason:
            return Response(
                {"detail": "追加の案内はすでに表示済みです。"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        latest = conversation.messages.filter(role=SupportMessage.Role.USER).order_by("-id").first()
        result = answer_support_followup(
            conversation.store,
            request.user,
            conversation.user_role,
            latest.content if latest else conversation.summary,
            reason,
            conversation.page_path,
        )
        SupportMessage.objects.create(
            conversation=conversation,
            role=SupportMessage.Role.USER,
            content=f"解決しなかった点: {result['reason']}",
        )
        assistant_message = SupportMessage.objects.create(
            conversation=conversation,
            role=SupportMessage.Role.ASSISTANT,
            content=result["answer"],
            sources=result["sources"],
        )
        conversation.unresolved_reason = result["reason"]
        conversation.unresolved_at = conversation.unresolved_at or timezone.now()
        conversation.status = SupportConversation.Status.OPEN
        conversation.save(update_fields=["unresolved_reason", "unresolved_at", "status", "updated_at"])

        since = timezone.now() - timedelta(days=14)
        related = SupportConversation.objects.filter(
            store=conversation.store,
            kind=SupportConversation.Kind.SUPPORT,
            user_role=conversation.user_role,
            page_path=conversation.page_path,
            unresolved_at__gte=since,
        )
        unique_count = len(set(related.values_list("user_id", flat=True)))
        trend_notified = False
        if unique_count >= 3 and not related.filter(trend_notified_at__gte=since).exists():
            trend_notified = notify_support_trend_slack(conversation, unique_count)
            if trend_notified:
                conversation.trend_notified_at = timezone.now()
                conversation.save(update_fields=["trend_notified_at", "updated_at"])
        return Response({
            "ok": True,
            "answer": assistant_message.content,
            "sources": assistant_message.sources,
            "mode": result["mode"],
            "unresolved_count": unique_count,
            "trend_notified": trend_notified,
        })


class SupportConversationEscalateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="support_conversation_escalate",
        request=OpenApiTypes.OBJECT,
        responses=OpenApiTypes.OBJECT,
    )
    def post(self, request, conversation_id):
        conversation = _accessible_conversation(request, conversation_id)
        if conversation is None or conversation.user_id != request.user.id:
            return Response({"detail": "会話が見つかりません。"}, status=status.HTTP_404_NOT_FOUND)
        if conversation.kind != SupportConversation.Kind.SUPPORT:
            return Response({"detail": "この受付は問い合わせへ変更できません。"}, status=status.HTTP_400_BAD_REQUEST)
        reason = conversation.unresolved_reason
        if len(reason) < 5:
            return Response(
                {"detail": "先に解決しなかった点を入力し、追加案内をご確認ください。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        conversation.status = SupportConversation.Status.ESCALATED
        conversation.summary = reason
        conversation.unresolved_reason = reason
        conversation.unresolved_at = conversation.unresolved_at or timezone.now()
        conversation.inquiry_submitted_at = timezone.now()
        conversation.escalated_at = timezone.now()
        conversation.slack_error = ""
        draft = prepare_support_reply_draft(conversation)
        conversation.ai_reply_draft = draft["draft"]
        conversation.auto_reply_scheduled_at = draft["scheduled_at"]
        conversation.auto_reply_sent_at = None
        conversation.auto_reply_cancelled_at = None
        conversation.save(update_fields=[
            "status", "summary", "unresolved_reason", "unresolved_at",
            "inquiry_submitted_at", "escalated_at", "slack_error",
            "ai_reply_draft", "auto_reply_scheduled_at", "auto_reply_sent_at",
            "auto_reply_cancelled_at", "updated_at",
        ])

        slack_notified = notify_support_slack(conversation)
        if slack_notified:
            conversation.slack_notified_at = timezone.now()
            conversation.save(update_fields=["slack_notified_at", "updated_at"])
        return Response({
            "ok": True,
            "status": conversation.status,
            "slack_notified": slack_notified,
            "auto_reply_scheduled_at": conversation.auto_reply_scheduled_at,
        })


class SupportFeatureRequestView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="support_feature_request_create",
        request=OpenApiTypes.OBJECT,
        responses=OpenApiTypes.OBJECT,
    )
    def post(self, request):
        store, role = _support_context(request)
        if store is None:
            return Response(
                {"detail": "この店舗の受付を利用する権限がありません。"},
                status=status.HTTP_403_FORBIDDEN,
            )
        details = redact_sensitive_text(request.data.get("details") or "")
        if len(details) < 5:
            return Response(
                {"detail": "ご意見・機能要望を5文字以上で入力してください。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        recent_count = SupportConversation.objects.filter(
            user=request.user,
            kind=SupportConversation.Kind.FEATURE_REQUEST,
            created_at__gte=timezone.now() - timedelta(hours=1),
        ).count()
        if recent_count >= 5:
            return Response(
                {"detail": "短時間の送信数が上限に達しました。しばらくしてからお試しください。"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        now = timezone.now()
        conversation = SupportConversation.objects.create(
            store=store,
            user=request.user,
            user_role=role,
            page_path=str(request.data.get("page_path") or "")[:500],
            page_title=str(request.data.get("page_title") or "")[:200],
            kind=SupportConversation.Kind.FEATURE_REQUEST,
            status=SupportConversation.Status.ESCALATED,
            summary=details,
            inquiry_submitted_at=now,
            escalated_at=now,
        )
        SupportMessage.objects.create(
            conversation=conversation,
            role=SupportMessage.Role.USER,
            content=details,
        )
        acknowledgement = SupportMessage.objects.create(
            conversation=conversation,
            role=SupportMessage.Role.ASSISTANT,
            content=(
                "ご意見・機能要望を受け付けました。今後の改善検討に活用します。"
                "個別の実装時期をお約束するものではありません。"
            ),
        )
        slack_notified = notify_support_slack(conversation)
        if slack_notified:
            conversation.slack_notified_at = timezone.now()
            conversation.save(update_fields=["slack_notified_at", "updated_at"])
        return Response({
            "ok": True,
            "conversation_id": conversation.id,
            "acknowledgement": acknowledgement.content,
            "status": conversation.status,
            "slack_notified": slack_notified,
        })


class MySupportConversationListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="my_support_conversation_list", responses=OpenApiTypes.OBJECT)
    def get(self, request):
        conversations = SupportConversation.objects.filter(user=request.user).select_related("store")[:100]
        return Response({"results": [_serialize_conversation(item) for item in conversations]})


class MySupportConversationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="my_support_conversation_detail", responses=OpenApiTypes.OBJECT)
    def get(self, request, conversation_id):
        conversation = get_object_or_404(
            SupportConversation.objects.select_related("store").prefetch_related("messages"),
            pk=conversation_id,
            user=request.user,
        )
        conversation.user_last_viewed_at = timezone.now()
        conversation.save(update_fields=["user_last_viewed_at", "updated_at"])
        return Response(_serialize_conversation(conversation, include_messages=True))


class SupportConversationListView(APIView):
    permission_classes = [IsAuthenticated, IsManager]

    @extend_schema(
        operation_id="support_conversation_list",
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        profile = request.user.profile
        conversations = SupportConversation.objects.filter(store=profile.store).select_related("store")
        requested_status = (request.query_params.get("status") or "").strip().upper()
        if requested_status in SupportConversation.Status.values:
            conversations = conversations.filter(status=requested_status)
        return Response({
            "results": [_serialize_conversation(item) for item in conversations[:200]],
        })


class SupportConversationDetailView(APIView):
    permission_classes = [IsAuthenticated, IsManager]

    @extend_schema(
        operation_id="support_conversation_detail",
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request, conversation_id):
        conversation = get_object_or_404(
            SupportConversation.objects.select_related("store").prefetch_related("messages"),
            pk=conversation_id,
            store=request.user.profile.store,
        )
        return Response(_serialize_conversation(conversation, include_messages=True))


class SupportConversationReplyView(APIView):
    permission_classes = [IsAuthenticated, IsManager]

    @extend_schema(
        operation_id="support_conversation_reply",
        request=OpenApiTypes.OBJECT,
        responses=OpenApiTypes.OBJECT,
    )
    def post(self, request, conversation_id):
        conversation = get_object_or_404(
            SupportConversation,
            pk=conversation_id,
            store=request.user.profile.store,
        )
        message = redact_sensitive_text(request.data.get("message") or "")
        if len(message) < 2:
            return Response({"detail": "返信を入力してください。"}, status=status.HTTP_400_BAD_REQUEST)
        support_message = SupportMessage.objects.create(
            conversation=conversation,
            role=SupportMessage.Role.OPERATOR,
            content=message,
        )
        conversation.status = SupportConversation.Status.RESOLVED
        conversation.resolved_at = timezone.now()
        conversation.auto_reply_cancelled_at = timezone.now()
        conversation.auto_reply_scheduled_at = None
        conversation.save(update_fields=[
            "status", "resolved_at", "auto_reply_cancelled_at",
            "auto_reply_scheduled_at", "updated_at",
        ])
        return Response({"ok": True, "message": _serialize_message(support_message)})


class SupportConversationCancelAutoReplyView(APIView):
    permission_classes = [IsAuthenticated, IsManager]

    @extend_schema(
        operation_id="support_conversation_cancel_auto_reply",
        request=OpenApiTypes.OBJECT,
        responses=OpenApiTypes.OBJECT,
    )
    def post(self, request, conversation_id):
        conversation = get_object_or_404(
            SupportConversation,
            pk=conversation_id,
            store=request.user.profile.store,
        )
        conversation.auto_reply_cancelled_at = timezone.now()
        conversation.auto_reply_scheduled_at = None
        conversation.save(update_fields=["auto_reply_cancelled_at", "auto_reply_scheduled_at", "updated_at"])
        return Response({"ok": True})
