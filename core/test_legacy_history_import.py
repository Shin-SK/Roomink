import csv
import io
from unittest.mock import patch

from django.core.management.base import CommandError
from django.test import TestCase

from core.models import Customer, LegacyCustomerHistory, Order, SmsLog, CallLog, CallNote
from core.services.legacy_history_import import CUSTOMER_HEADERS, ORDER_HEADERS, import_histories
from core.tests import RoomankOpsSmokeTestBase


def csv_bytes(headers, rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(headers)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8-sig")


def exports():
    customers = csv_bytes(CUSTOMER_HEADERS, [
        ["1", "101", "架空顧客", "09000000001", "", "", "", ""],
        ["2", "102", "番号不明の架空顧客", "不明", "", "", "", ""],
    ])
    def order(number, customer):
        return [str(number), customer, "架空顧客", "2026/9/30", "23:30", "受付", "架空担当", "架空90分", "フリー", "", "", "0", "", "", "", "現金", "18000", "9000", "9000", "原文メモ"]
    orders = csv_bytes(ORDER_HEADERS, [order(1, "101"), order(2, "102"), ["", "", "", "", "", "", "", "", "", "", "", "0", "", "", "", "", "36000", "18000", "18000", ""]])
    return customers, orders


class LegacyHistoryImportTest(RoomankOpsSmokeTestBase):
    def setUp(self):
        super().setUp()
        self.customer.staff_memo = "注意事項\n旧顧客ID: 101"
        self.customer.legacy_usage_history = "既存の原文"
        self.customer.save()
        self.customers, self.orders = exports()

    def run_import(self, **options):
        return import_histories(store_id=self.store_a.id, customer_bytes=self.customers, order_bytes=self.orders, **options)

    def test_dry_run_and_apply_are_reference_only_and_preserve_every_order(self):
        before = {m: m.objects.count() for m in (Customer, Order, SmsLog, CallLog)}
        preview = self.run_import()
        self.assertEqual(preview["orders"], 2)
        self.assertEqual(preview["excluded_summary_rows"], 1)
        self.assertEqual(LegacyCustomerHistory.objects.count(), 0)
        result = self.run_import(apply=True, expected_fingerprint=preview["fingerprint"])
        self.assertEqual(result["created"], 2)
        linked = LegacyCustomerHistory.objects.get(legacy_customer_id="101")
        self.assertEqual(linked.customer, self.customer)
        self.assertIn("架空担当", linked.history_text)
        self.assertNotIn("9000", linked.history_text)
        unlinked = LegacyCustomerHistory.objects.get(legacy_customer_id="102")
        self.assertIsNone(unlinked.customer)
        self.assertEqual(unlinked.link_reason, "invalid_phone")
        self.assertEqual({m: m.objects.count() for m in before}, before)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.legacy_usage_history, "既存の原文")
        self.assertEqual(self.customer.staff_memo, "注意事項\n旧顧客ID: 101")

    def test_repeated_apply_is_idempotent_and_changed_source_never_overwrites(self):
        preview = self.run_import()
        self.run_import(apply=True, expected_fingerprint=preview["fingerprint"])
        again = self.run_import(apply=True, expected_fingerprint=preview["fingerprint"])
        self.assertEqual(again["created"], 0)
        self.assertEqual(again["unchanged"], 2)
        with self.assertRaises(CommandError):
            self.run_import(apply=True, expected_fingerprint="wrong")
        self.orders = self.orders.replace("原文メモ".encode(), "別メモ".encode())
        with self.assertRaises(CommandError):
            self.run_import()
        self.assertEqual(LegacyCustomerHistory.objects.count(), 2)

    def test_invalid_order_or_duplicate_customer_aborts_before_any_write(self):
        self.orders = self.orders.replace(b"2026/9/30", b"invalid-date")
        with self.assertRaises(CommandError):
            self.run_import()
        self.assertEqual(LegacyCustomerHistory.objects.count(), 0)

    def test_customer_matching_never_uses_another_store_or_ambiguous_legacy_id(self):
        Customer.objects.create(store=self.store_b, phone="09000000001", staff_memo="旧顧客ID: 101")
        Customer.objects.create(store=self.store_a, phone="09000000002", staff_memo="旧顧客ID: 101")
        preview = self.run_import()
        self.run_import(apply=True, expected_fingerprint=preview["fingerprint"])
        self.assertIsNone(LegacyCustomerHistory.objects.get(legacy_customer_id="101").customer)

    def test_api_and_cti_enforce_store_and_role_boundaries(self):
        preview = self.run_import()
        self.run_import(apply=True, expected_fingerprint=preview["fingerprint"])
        entry = LegacyCustomerHistory.objects.get(legacy_customer_id="101")
        other = self.client_as(self.manager_b)
        self.assertEqual(other.get(f"/api/op/legacy-histories/{entry.pk}/").status_code, 404)
        own = self.client_as(self.manager_a)
        self.assertEqual(own.get(f"/api/op/legacy-histories/{entry.pk}/").status_code, 200)
        self.assertNotIn("history_text", own.get("/api/op/legacy-histories/").data["results"][0])
        self.assertEqual(own.post("/api/op/legacy-histories/", {}, format="json").status_code, 405)
        self.assertEqual(self.client_as(self.cast_user_a).get("/api/op/legacy-histories/").status_code, 403)
        call = CallLog.objects.create(store=self.store_a, contact_id="legacy-cti", customer=self.customer, from_phone=self.customer.phone, to_phone="")
        response = own.get(f"/api/op/cti/calls/{call.pk}/context/")
        self.assertEqual(response.data["customer_history"]["legacy_records"], [{"id": entry.pk, "visit_count": 1}])
        call.customer = None
        call.save()
        response = own.get(f"/api/op/cti/calls/{call.pk}/context/")
        self.assertEqual(response.data["customer_history"]["legacy_records"], [])


class CtiInquiryMemoTest(RoomankOpsSmokeTestBase):
    def setUp(self):
        super().setUp()
        self.call = CallLog.objects.create(store=self.store_a, contact_id="memo-only-fixture", from_phone=self.customer.phone, to_phone="", customer=self.customer)
        self.url = f"/api/op/cti/calls/{self.call.pk}/notes/"

    def test_save_and_complete_is_atomic_idempotent_and_creates_no_booking_or_sms(self):
        client = self.client_as(self.manager_a)
        before = (Order.objects.count(), Customer.objects.count(), SmsLog.objects.count())
        body = {"body": "満席のため後日問い合わせ", "complete_reception": True}
        for expected in (201, 200):
            response = client.post(self.url, body, format="json", HTTP_X_ROOMINK_CALL=str(self.call.pk))
            self.assertEqual(response.status_code, expected, response.data)
        self.assertEqual(CallNote.objects.filter(call=self.call).count(), 1)
        self.call.refresh_from_db()
        self.assertEqual(self.call.status, CallLog.Status.DONE)
        self.assertEqual((Order.objects.count(), Customer.objects.count(), SmsLog.objects.count()), before)
        ctx = client.get(f"/api/op/cti/calls/{self.call.pk}/context/").data
        self.assertEqual(ctx["customer_history"]["current_notes"][0]["body"], body["body"])

    def test_save_failure_rolls_back_note_and_completion(self):
        with patch.object(CallLog, "save", side_effect=RuntimeError("fixture failure")):
            with self.assertRaises(RuntimeError):
                self.client_as(self.manager_a).post(self.url, {"body": "保存できないメモ", "complete_reception": True}, format="json")
        self.assertFalse(CallNote.objects.filter(call=self.call).exists())
        self.call.refresh_from_db()
        self.assertEqual(self.call.status, CallLog.Status.NEW)

    def test_blank_long_invalid_and_forbidden_requests_change_nothing(self):
        client = self.client_as(self.manager_a)
        for body in ({"body": " "}, {"body": "a" * 2001}, {"body": 1}, {"body": "x", "complete_reception": "true"}):
            self.assertEqual(client.post(self.url, body, format="json").status_code, 400)
        self.assertEqual(self.client_as(self.manager_b).post(self.url, {"body": "x"}, format="json").status_code, 404)
        self.assertEqual(self.client_as(self.cast_user_a).post(self.url, {"body": "x"}, format="json").status_code, 403)
        self.assertFalse(CallNote.objects.exists())

    def test_memo_without_customer_and_without_completion_remains_a_call_note(self):
        self.call.customer = None
        self.call.save()
        response = self.client_as(self.manager_a).post(self.url, {"body": "新規の問い合わせ"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.call.refresh_from_db()
        self.assertEqual(self.call.status, CallLog.Status.NEW)
