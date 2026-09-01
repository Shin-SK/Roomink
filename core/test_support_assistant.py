import json
import os
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from .models import (
    Cast,
    CastNote,
    Customer,
    Store,
    SupportConversation,
    SupportMessage,
    UserProfile,
)


class SupportAssistantApiTests(APITestCase):
    def setUp(self):
        self.store = Store.objects.create(name="アールズスパ", slug="rs-spa")
        self.other_store = Store.objects.create(name="別店舗", slug="other-store")

        self.manager = get_user_model().objects.create_user("support-manager", password="pass")
        UserProfile.objects.create(
            user=self.manager,
            store=self.store,
            role=UserProfile.Role.MANAGER,
        )
        self.manager_client = APIClient()
        self.manager_client.force_authenticate(self.manager)

        self.other_manager = get_user_model().objects.create_user("other-manager", password="pass")
        UserProfile.objects.create(
            user=self.other_manager,
            store=self.other_store,
            role=UserProfile.Role.MANAGER,
        )
        self.other_manager_client = APIClient()
        self.other_manager_client.force_authenticate(self.other_manager)

        self.customer_user = get_user_model().objects.create_user("support-customer", password="pass")
        Customer.objects.create(
            user=self.customer_user,
            store=self.store,
            phone="09000000001",
            display_name="問い合わせテスト",
        )
        self.customer_client = APIClient()
        self.customer_client.force_authenticate(self.customer_user)

    def _chat(self, client=None, **overrides):
        body = {
            "message": "カード決済後のSMSはどこから送れますか？",
            "page_path": "/op/orders/123",
            "page_title": "予約詳細",
        }
        body.update(overrides)
        return (client or self.manager_client).post("/api/support/chat/", body, format="json")

    def test_anonymous_user_cannot_use_support(self):
        response = APIClient().post(
            "/api/support/chat/",
            {"message": "使い方を教えて"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(SupportConversation.objects.count(), 0)

    @patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False)
    def test_fallback_answer_is_saved_with_page_and_store_context(self):
        response = self._chat(message="カード決済後のSMSはどこから送れますか？ 090-1234-5678")

        self.assertEqual(response.status_code, 200)
        self.assertIn("予約詳細", response.data["answer"])
        self.assertTrue(response.data["sources"])
        conversation = SupportConversation.objects.get()
        self.assertEqual(conversation.store, self.store)
        self.assertEqual(conversation.user_role, UserProfile.Role.MANAGER)
        self.assertEqual(conversation.page_path, "/op/orders/123")
        user_message = conversation.messages.get(role=SupportMessage.Role.USER)
        self.assertNotIn("090-1234-5678", user_message.content)

    def test_manager_cannot_read_another_store_conversation(self):
        response = self._chat()
        conversation_id = response.data["conversation_id"]

        listing = self.other_manager_client.get("/api/op/support/conversations/")
        detail = self.other_manager_client.get(
            f"/api/op/support/conversations/{conversation_id}/",
        )

        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["results"], [])
        self.assertEqual(detail.status_code, 404)

    def test_customer_must_use_a_store_linked_to_their_account(self):
        allowed = self._chat(
            self.customer_client,
            message="予約内容はどこで確認できますか？",
            page_path="/s/rs-spa/mypage",
            store_slug="rs-spa",
        )
        denied = self._chat(
            self.customer_client,
            message="予約内容はどこで確認できますか？",
            page_path="/s/other-store/mypage",
            store_slug="other-store",
        )

        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(SupportConversation.objects.count(), 1)

    @patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False)
    def test_cast_only_receives_notes_addressed_to_them(self):
        cast_user = get_user_model().objects.create_user("support-cast", password="pass")
        UserProfile.objects.create(
            user=cast_user,
            store=self.store,
            role=UserProfile.Role.CAST,
        )
        own_cast = Cast.objects.create(store=self.store, user=cast_user, name="本人")
        other_cast = Cast.objects.create(store=self.store, name="別キャスト")
        own_note = CastNote.objects.create(
            store=self.store,
            title="本人向け秘密手順",
            body="青い受付票の扱い方です。",
            status=CastNote.Status.PUBLISHED,
            visibility=CastNote.Visibility.CAST,
        )
        own_note.target_casts.add(own_cast)
        other_note = CastNote.objects.create(
            store=self.store,
            title="別キャスト専用の秘密手順",
            body="赤い受付票の扱い方です。",
            status=CastNote.Status.PUBLISHED,
            visibility=CastNote.Visibility.CAST,
        )
        other_note.target_casts.add(other_cast)
        client = APIClient()
        client.force_authenticate(cast_user)

        response = self._chat(
            client,
            message="秘密手順と受付票について教えて",
            page_path="/cast/mypage",
        )

        self.assertEqual(response.status_code, 200)
        titles = [source["title"] for source in response.data["sources"]]
        self.assertIn("店舗ノート: 本人向け秘密手順", titles)
        self.assertNotIn("店舗ノート: 別キャスト専用の秘密手順", titles)

    @override_settings(SUPPORT_SLACK_WEBHOOK_URL="")
    @patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False)
    def test_unresolved_conversation_is_escalated_without_external_send(self):
        response = self._chat()
        conversation_id = response.data["conversation_id"]

        followup = self.manager_client.post(
            f"/api/support/conversations/{conversation_id}/unresolved/",
            {"reason": "案内されたボタンが画面に見つかりません"},
            format="json",
        )

        escalation = self.manager_client.post(
            f"/api/support/conversations/{conversation_id}/escalate/",
            {},
            format="json",
        )

        self.assertEqual(followup.status_code, 200)
        self.assertTrue(followup.data["answer"])
        self.assertEqual(escalation.status_code, 200)
        self.assertFalse(escalation.data["slack_notified"])
        conversation = SupportConversation.objects.get(pk=conversation_id)
        self.assertEqual(conversation.status, SupportConversation.Status.ESCALATED)
        self.assertIsNotNone(conversation.escalated_at)

    @patch("core.support_views.notify_support_trend_slack")
    @patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False)
    def test_unresolved_feedback_does_not_notify_until_three_unique_users(self, mocked_notify):
        mocked_notify.return_value = True
        first = self._chat()
        first_feedback = self.manager_client.post(
            f"/api/support/conversations/{first.data['conversation_id']}/unresolved/",
            {"reason": "案内の場所が見つかりません"},
            format="json",
        )
        self.assertEqual(first_feedback.status_code, 200)
        self.assertFalse(first_feedback.data["trend_notified"])
        mocked_notify.assert_not_called()

        for index in range(2):
            user = get_user_model().objects.create_user(f"support-staff-{index}", password="pass")
            UserProfile.objects.create(user=user, store=self.store, role=UserProfile.Role.MANAGER)
            client = APIClient()
            client.force_authenticate(user)
            chat = self._chat(client)
            feedback = client.post(
                f"/api/support/conversations/{chat.data['conversation_id']}/unresolved/",
                {"reason": f"案内の場所が見つかりません {index}"},
                format="json",
            )
            self.assertEqual(feedback.status_code, 200)

        unresolved_users = list(
            SupportConversation.objects.filter(unresolved_at__isnull=False)
            .values_list("user_id", "page_path")
        )
        self.assertEqual(feedback.data["unresolved_count"], 3, unresolved_users)
        mocked_notify.assert_called_once()

    @patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False)
    def test_inquiry_requires_followup_and_creates_a_draft(self):
        response = self._chat()
        conversation_id = response.data["conversation_id"]

        invalid = self.manager_client.post(
            f"/api/support/conversations/{conversation_id}/escalate/",
            {},
            format="json",
        )
        followup = self.manager_client.post(
            f"/api/support/conversations/{conversation_id}/unresolved/",
            {"reason": "案内されたボタンが画面に見つかりません"},
            format="json",
        )
        submitted = self.manager_client.post(
            f"/api/support/conversations/{conversation_id}/escalate/",
            {},
            format="json",
        )

        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(followup.status_code, 200)
        self.assertEqual(submitted.status_code, 200)
        conversation = SupportConversation.objects.get(pk=conversation_id)
        self.assertEqual(conversation.status, SupportConversation.Status.ESCALATED)
        self.assertTrue(conversation.ai_reply_draft)
        self.assertIsNotNone(conversation.inquiry_submitted_at)

    def test_manager_reply_is_visible_in_owner_history(self):
        response = self._chat(self.customer_client, store_slug="rs-spa")
        conversation_id = response.data["conversation_id"]
        self.customer_client.post(
            f"/api/support/conversations/{conversation_id}/unresolved/",
            {"reason": "案内された場所を開いても予約が表示されません"},
            format="json",
        )
        self.customer_client.post(
            f"/api/support/conversations/{conversation_id}/escalate/",
            {},
            format="json",
        )

        blocked = self.other_manager_client.post(
            f"/api/op/support/conversations/{conversation_id}/reply/",
            {"message": "別店舗からの返信"},
            format="json",
        )
        replied = self.manager_client.post(
            f"/api/op/support/conversations/{conversation_id}/reply/",
            {"message": "店舗専用URLからもう一度開いてください。"},
            format="json",
        )
        history = self.customer_client.get(f"/api/support/conversations/{conversation_id}/")

        self.assertEqual(blocked.status_code, 404)
        self.assertEqual(replied.status_code, 200)
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.data["messages"][-1]["role"], SupportMessage.Role.OPERATOR)
        self.assertEqual(history.data["status"], SupportConversation.Status.RESOLVED)

    @override_settings(SUPPORT_SLACK_WEBHOOK_URL="")
    def test_feature_request_is_stored_separately_without_ai_answer(self):
        response = self.manager_client.post(
            "/api/support/feature-requests/",
            {
                "details": "予約一覧の検索条件を保存できるようにしてほしい",
                "page_path": "/op/orders",
                "page_title": "予約一覧",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        conversation = SupportConversation.objects.get(pk=response.data["conversation_id"])
        self.assertEqual(conversation.kind, SupportConversation.Kind.FEATURE_REQUEST)
        self.assertEqual(conversation.status, SupportConversation.Status.ESCALATED)
        self.assertFalse(conversation.ai_reply_draft)
        self.assertIn("実装時期", response.data["acknowledgement"])

    def test_other_store_manager_cannot_read_feature_request(self):
        response = self.manager_client.post(
            "/api/support/feature-requests/",
            {"details": "店舗画面の色を選べるようにしてほしい"},
            format="json",
        )

        detail = self.other_manager_client.get(
            f"/api/op/support/conversations/{response.data['conversation_id']}/",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(detail.status_code, 404)

    @override_settings(SUPPORT_AUTO_REPLY_ENABLED=True)
    def test_due_auto_reply_is_sent_by_command(self):
        response = self._chat()
        conversation = SupportConversation.objects.get(pk=response.data["conversation_id"])
        conversation.status = SupportConversation.Status.ESCALATED
        conversation.ai_reply_draft = "操作案内の自動返信です。"
        conversation.auto_reply_scheduled_at = timezone.now() - timedelta(minutes=1)
        conversation.save()

        output = StringIO()
        call_command("process_support_auto_replies", stdout=output)

        conversation.refresh_from_db()
        self.assertEqual(conversation.status, SupportConversation.Status.RESOLVED)
        self.assertIsNotNone(conversation.auto_reply_sent_at)
        self.assertTrue(
            conversation.messages.filter(
                role=SupportMessage.Role.ASSISTANT,
                content="操作案内の自動返信です。",
            ).exists(),
        )

    def test_only_owner_or_same_store_manager_can_resolve(self):
        response = self._chat(self.customer_client, store_slug="rs-spa")
        conversation_id = response.data["conversation_id"]

        blocked = self.other_manager_client.post(
            f"/api/support/conversations/{conversation_id}/resolve/",
            {},
            format="json",
        )
        resolved = self.manager_client.post(
            f"/api/support/conversations/{conversation_id}/resolve/",
            {},
            format="json",
        )

        self.assertEqual(blocked.status_code, 404)
        self.assertEqual(resolved.status_code, 200)
        self.assertEqual(
            SupportConversation.objects.get(pk=conversation_id).status,
            SupportConversation.Status.RESOLVED,
        )

    @override_settings(
        OPENAI_API_KEY="test-key",
        OPENAI_SUPPORT_MODEL="gpt-5-mini",
        OPENAI_SUPPORT_API_URL="https://api.openai.com/v1/responses",
    )
    @patch("core.services.support_assistant.urlopen")
    def test_openai_request_disables_storage_and_redacts_personal_data(self, mocked_urlopen):
        mocked_urlopen.return_value.__enter__.return_value.read.return_value = json.dumps({
            "output_text": "予約詳細画面の「決済確認後SMSを送る」から送信できます。",
        }).encode("utf-8")

        response = self._chat(
            message="090-1234-5678 と test@example.com の予約でSMSはどこ？",
        )

        self.assertEqual(response.status_code, 200)
        request = mocked_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertFalse(payload["store"])
        self.assertEqual(payload["max_output_tokens"], 1200)
        self.assertNotIn("090-1234-5678", payload["input"])
        self.assertNotIn("test@example.com", payload["input"])
        self.assertEqual(response.data["mode"], "ai")

    @override_settings(
        OPENAI_API_KEY="test-key",
        OPENAI_SUPPORT_MODEL="gpt-5-mini",
        OPENAI_SUPPORT_API_URL="https://api.openai.com/v1/responses",
    )
    @patch("core.services.support_assistant.urlopen")
    def test_incomplete_openai_response_uses_complete_fallback(self, mocked_urlopen):
        mocked_urlopen.return_value.__enter__.return_value.read.return_value = json.dumps({
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output_text": "回答（画面／別の",
        }).encode("utf-8")

        response = self._chat(message="カード決済後のSMSはどこ？")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["mode"], "fallback")
        self.assertNotEqual(response.data["answer"], "回答（画面／別の")
        self.assertIn("決済確認後SMSを送る", response.data["answer"])
