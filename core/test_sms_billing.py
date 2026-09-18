from datetime import datetime
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import SmsLog, Store, UserProfile
from core.services.sms_billing import sms_usage_summary


User = get_user_model()


class SmsBillingTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="SMS料金テスト店", timezone="Asia/Tokyo")
        self.other_store = Store.objects.create(name="別店舗", timezone="Asia/Tokyo")
        self.manager = User.objects.create_user("sms_billing_manager")
        UserProfile.objects.create(
            user=self.manager,
            store=self.store,
            role=UserProfile.Role.MANAGER,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.manager)
        self.month = datetime(2026, 9, 1).date()

    def create_log(self, store, segments, **overrides):
        values = {
            "store": store,
            "to_phone": "09000000001",
            "body": "[予約リンク]",
            "status": SmsLog.Status.SENT,
            "provider": SmsLog.Provider.TWILIO,
            "provider_message_id": f"SM{store.id}{SmsLog.objects.count()}",
            "template_type": SmsLog.TemplateType.RESERVATION_CONFIRMATION,
            "segment_count": segments,
        }
        values.update(overrides)
        log = SmsLog.objects.create(**values)
        SmsLog.objects.filter(pk=log.pk).update(
            sent_at=datetime(2026, 9, 10, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
        )
        return log

    def test_200_is_included_and_386_is_two_extra_blocks(self):
        self.create_log(self.store, 200)
        included = sms_usage_summary(self.store, self.month)
        self.assertEqual(included["used_segments"], 200)
        self.assertEqual(included["extra_blocks"], 0)
        self.assertEqual(included["list_price"], 19_800)

        self.create_log(self.store, 186)
        increased = sms_usage_summary(self.store, self.month)
        self.assertEqual(increased["used_segments"], 386)
        self.assertEqual(increased["extra_blocks"], 2)
        self.assertEqual(increased["current_block_limit"], 400)
        self.assertEqual(increased["list_price"], 29_800)
        self.assertEqual(increased["remaining_in_block"], 14)

    def test_only_customer_billable_attempts_in_month_and_store_are_counted(self):
        self.create_log(self.store, 2)
        self.create_log(self.other_store, 8)
        self.create_log(
            self.store,
            7,
            template_type=SmsLog.TemplateType.CAST_NOTICE,
        )
        self.create_log(
            self.store,
            9,
            status=SmsLog.Status.CONFIG_MISSING,
            provider=SmsLog.Provider.NONE,
            provider_message_id="",
        )
        old = self.create_log(self.store, 5)
        SmsLog.objects.filter(pk=old.pk).update(
            sent_at=datetime(2026, 8, 31, 23, 59, tzinfo=ZoneInfo("Asia/Tokyo")),
        )

        summary = sms_usage_summary(self.store, self.month)

        self.assertEqual(summary["used_segments"], 2)

    def test_exempt_store_keeps_usage_and_list_price_but_bills_zero(self):
        self.store.sms_billing_exempt = True
        self.store.save(update_fields=["sms_billing_exempt"])
        self.create_log(self.store, 301)

        summary = sms_usage_summary(self.store, self.month)

        self.assertTrue(summary["billing_exempt"])
        self.assertEqual(summary["list_price"], 29_800)
        self.assertEqual(summary["billed_price"], 0)

    def test_api_is_store_scoped_and_rejects_invalid_month(self):
        self.create_log(self.store, 12)
        self.create_log(self.other_store, 99)

        response = self.client.get("/api/op/sms-usage/?month=2026-09")
        invalid = self.client.get("/api/op/sms-usage/?month=2026-13")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["used_segments"], 12)
        self.assertEqual(invalid.status_code, 400, invalid.data)
