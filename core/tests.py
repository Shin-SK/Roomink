"""
Roomink Ops スモークテスト（Django test client / DRF APIClient ベース）。

今回追加した5機能を中心に、以下を確認する:
  1. エリアタグ付き売上集計（Room.area_name → /op/sales-dashboard/ の by_area）
  2. ノート/施術マニュアル（CastNote CRUD・cast側閲覧・store分離）
  3. 出勤確認の外部通知の土台（ShiftConfirmNotificationLog・テストログ作成・実送信なし）
  4. PayPay/カード手数料の精算反映（Order.PaymentMethod.PAYPAY・手数料設定・sales-dashboardの手数料見込み）
  5. シフト申請CSV戻し承認の土台（export_csv → import_preview → import_apply、既存承認ロジック再利用）

既存機能（DailySettlementView, CastDailyCheckout, CastAdjustment, Order の基本挙動）を壊していないことも
あわせて確認する。外部API送信・本番DB操作は一切行わない（テストはDjangoのテスト用DBのみを使用する）。

実行方法:
    python3 manage.py test core
"""
import csv
import io
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import (
    Cast, CastAdjustment, CastDailyCheckout, CastNote, Course, Customer,
    Order, Room, ShiftAssignment, ShiftConfirmNotificationLog, ShiftRequest,
    Store, UserProfile,
)

User = get_user_model()


def make_store(name):
    return Store.objects.create(name=name)


def make_manager(store, username):
    user = User.objects.create_user(username=username, password="pass1234")
    UserProfile.objects.create(user=user, store=store, role=UserProfile.Role.MANAGER)
    return user


def make_cast(store, username, name):
    user = User.objects.create_user(username=username, password="pass1234")
    UserProfile.objects.create(user=user, store=store, role=UserProfile.Role.CAST)
    cast = Cast.objects.create(store=store, user=user, name=name)
    return user, cast


class RoomankOpsSmokeTestBase(TestCase):
    """共通フィクスチャ: 2店舗（A/B）・manager/cast・ルーム・コース・顧客を用意する。
    store分離の確認に使うため、必ず2店舗分作成する。"""

    def setUp(self):
        self.store_a = make_store("スモークテスト店舗A")
        self.store_b = make_store("スモークテスト店舗B")

        self.manager_a = make_manager(self.store_a, "smoke_manager_a")
        self.manager_b = make_manager(self.store_b, "smoke_manager_b")

        self.cast_user_a, self.cast_a = make_cast(self.store_a, "smoke_cast_a", "スモークキャストA")
        self.cast_user_b, self.cast_b = make_cast(self.store_b, "smoke_cast_b", "スモークキャストB")

        self.room_shinjuku = Room.objects.create(store=self.store_a, name="101号室", area_name="新宿")
        self.room_ikebukuro = Room.objects.create(store=self.store_a, name="201号室", area_name="池袋")
        self.room_noarea = Room.objects.create(store=self.store_a, name="301号室")  # 未設定エリア

        self.course = Course.objects.create(store=self.store_a, name="スモークコース60分", duration=60, price=10000)
        self.customer = Customer.objects.create(store=self.store_a, phone="09000000001", display_name="スモーク顧客")

    def client_as(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client


class AuthAndPermissionSmokeTest(RoomankOpsSmokeTestBase):
    """基本認証・権限チェック。既存の主要APIが未認証で403/401を返すことも確認する。"""

    def test_unauthenticated_requests_are_rejected(self):
        client = APIClient()
        res = client.get("/api/op/sales-dashboard/?range=today")
        self.assertIn(res.status_code, (401, 403))

    def test_manager_login_via_api(self):
        client = APIClient()
        res = client.post(
            "/api/auth/login/",
            {"username": "smoke_manager_a", "password": "pass1234"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        me = client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["role"], "manager")

    def test_cast_login_via_api(self):
        client = APIClient()
        res = client.post(
            "/api/auth/login/",
            {"username": "smoke_cast_a", "password": "pass1234"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        me = client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["role"], "cast")

    def test_cast_cannot_access_manager_only_endpoint(self):
        client = self.client_as(self.cast_user_a)
        res = client.get("/api/op/sales-dashboard/?range=today")
        self.assertEqual(res.status_code, 403)


class AreaSalesDashboardSmokeTest(RoomankOpsSmokeTestBase):
    """1. エリアタグ付き売上集計"""

    def test_room_area_name_editable_via_api(self):
        client = self.client_as(self.manager_a)
        res = client.patch(f"/api/rooms/{self.room_noarea.id}/", {"area_name": "五反田"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.room_noarea.refresh_from_db()
        self.assertEqual(self.room_noarea.area_name, "五反田")

        # 空欄に戻せる（未設定扱い）ことも確認
        res = client.patch(f"/api/rooms/{self.room_noarea.id}/", {"area_name": ""}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["area_name"], "")

    def test_sales_dashboard_includes_by_area(self):
        Order.objects.create(
            store=self.store_a, cast=self.cast_a, room=self.room_shinjuku, customer=self.customer,
            course=self.course, course_name=self.course.name, course_price=self.course.price,
            total_price=self.course.price,
            start=self._today_dt(10), end=self._today_dt(11),
            status=Order.Status.DONE, payment_method=Order.PaymentMethod.CASH,
        )
        client = self.client_as(self.manager_a)
        res = client.get("/api/op/sales-dashboard/?range=today")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("by_area", data)
        area_names = [a["area_name"] for a in data["by_area"]]
        self.assertIn("新宿", area_names)

    def _today_dt(self, hour):
        from django.utils import timezone
        return timezone.make_aware(timezone.datetime.combine(date.today(), timezone.datetime.min.time())).replace(hour=hour)


class CastNoteSmokeTest(RoomankOpsSmokeTestBase):
    """2. ノート/施術マニュアル機能"""

    def test_manager_can_create_and_publish_note_and_cast_can_read_it(self):
        mgr = self.client_as(self.manager_a)
        res = mgr.post("/api/cast-notes/", {
            "title": "施術マニュアル：スモークテスト",
            "category": "施術マニュアル",
            "body": "本文テスト",
            "visibility": "CAST",
        }, format="json")
        self.assertEqual(res.status_code, 201)
        note_id = res.json()["id"]
        self.assertEqual(res.json()["status"], "DRAFT")

        # 下書きのうちはcastから見えない
        cast_client = self.client_as(self.cast_user_a)
        res = cast_client.get("/api/cast/notes/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["pinned"]) + len(res.json()["recent"]), 0)

        # 公開するとcastから見える
        res = mgr.post(f"/api/cast-notes/{note_id}/publish/")
        self.assertEqual(res.status_code, 200)
        res = mgr.post(f"/api/cast-notes/{note_id}/pin/")
        self.assertEqual(res.status_code, 200)

        res = cast_client.get("/api/cast/notes/")
        self.assertEqual(res.status_code, 200)
        pinned_titles = [n["title"] for n in res.json()["pinned"]]
        self.assertIn("施術マニュアル：スモークテスト", pinned_titles)

    def test_note_is_store_scoped(self):
        CastNote.objects.create(
            store=self.store_a, title="A店ノート", status=CastNote.Status.PUBLISHED,
            visibility=CastNote.Visibility.CAST,
        )
        cast_b_client = self.client_as(self.cast_user_b)
        res = cast_b_client.get("/api/cast/notes/")
        self.assertEqual(res.status_code, 200)
        all_titles = [n["title"] for n in res.json()["pinned"] + res.json()["recent"]]
        self.assertNotIn("A店ノート", all_titles)

    def test_staff_cannot_manage_notes(self):
        # cast(=非manager)はノートの新規作成ができない
        cast_client = self.client_as(self.cast_user_a)
        res = cast_client.post("/api/cast-notes/", {"title": "不正作成"}, format="json")
        self.assertEqual(res.status_code, 403)


class ShiftConfirmNotificationSmokeTest(RoomankOpsSmokeTestBase):
    """3. 出勤確認の外部通知の土台（実送信は行わない）"""

    def test_alert_and_test_log_creation(self):
        from django.utils import timezone
        soon = (timezone.now() + timedelta(minutes=30)).time().replace(second=0, microsecond=0)
        shift = ShiftAssignment.objects.create(
            store=self.store_a, date=date.today(), cast=self.cast_a, room=self.room_shinjuku,
            start_time=soon, end_time=soon,
        )

        mgr = self.client_as(self.manager_a)
        res = mgr.get("/api/op/shift-confirm-alerts/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["external_send_supported"])
        alert = next((a for a in data["alerts"] if a["shift_id"] == shift.id), None)
        self.assertIsNotNone(alert)
        self.assertFalse(alert["has_notification_log"])

        # テストログ作成（実送信は行わない。SKIPPED状態のログのみ作成される）
        res = mgr.post(
            f"/api/op/shift-confirm-alerts/{shift.id}/mark_notification_test/",
            {"alert_level": alert["alert_level"], "target_type": "CAST"},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        log = res.json()
        self.assertEqual(log["channel"], "NONE")
        self.assertEqual(log["status"], "SKIPPED")

        # ログ一覧に反映される（LimitOffsetPaginationのため results キー配下）
        res = mgr.get("/api/shift-confirm-notification-logs/")
        self.assertEqual(res.status_code, 200)
        results = res.json()["results"]
        self.assertTrue(any(l["shift_assignment"] == shift.id for l in results))

        self.assertEqual(ShiftConfirmNotificationLog.objects.filter(store=self.store_a).count(), 1)

    def test_notification_log_is_store_scoped(self):
        shift_b = ShiftAssignment.objects.create(
            store=self.store_b, date=date.today(), cast=self.cast_b, room=Room.objects.create(store=self.store_b, name="B店ルーム"),
            start_time="10:00", end_time="11:00",
        )
        ShiftConfirmNotificationLog.objects.create(
            store=self.store_b, shift_assignment=shift_b, cast=self.cast_b,
            alert_level="TWO_HOURS", status="SKIPPED",
        )
        mgr_a = self.client_as(self.manager_a)
        res = mgr_a.get("/api/shift-confirm-notification-logs/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["results"]), 0)


class PaymentFeeSmokeTest(RoomankOpsSmokeTestBase):
    """4. PayPay/カード手数料の精算反映（参考値。確定精算・給与確定には接続しない）"""

    def test_payment_fee_settings_get_and_patch(self):
        mgr = self.client_as(self.manager_a)
        res = mgr.get("/api/op/payment-fee-settings/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["paypay_fee_rate"], 5)
        self.assertEqual(res.json()["card_fee_rate"], 10)

        res = mgr.patch("/api/op/payment-fee-settings/", {"paypay_fee_rate": 8}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["paypay_fee_rate"], 8)

    def test_order_accepts_paypay_payment_method(self):
        from django.utils import timezone
        order = Order.objects.create(
            store=self.store_a, cast=self.cast_a, room=self.room_shinjuku, customer=self.customer,
            course=self.course, course_name=self.course.name, course_price=self.course.price,
            total_price=self.course.price,
            start=timezone.now(), end=timezone.now() + timedelta(hours=1),
            status=Order.Status.DONE, payment_method=Order.PaymentMethod.PAYPAY,
        )
        self.assertEqual(order.payment_method, "PAYPAY")

        mgr = self.client_as(self.manager_a)
        res = mgr.get("/api/op/sales-dashboard/?range=today")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("payment_fee_estimate", data)
        self.assertIn("net_sales_after_payment_fee", data)
        paypay_row = next((r for r in data["by_payment_method"] if r["payment_method"] == "PAYPAY"), None)
        self.assertIsNotNone(paypay_row)
        self.assertEqual(paypay_row["fee_rate"], 5)

    def test_daily_settlement_view_not_broken_by_paypay_addition(self):
        """既存 DailySettlementView が壊れていないことの簡易確認（PAYPAY注文があってもエラーにならない）"""
        from django.utils import timezone
        ShiftAssignment.objects.create(
            store=self.store_a, date=date.today(), cast=self.cast_a, room=self.room_shinjuku,
            start_time="10:00", end_time="20:00",
        )
        Order.objects.create(
            store=self.store_a, cast=self.cast_a, room=self.room_shinjuku, customer=self.customer,
            course=self.course, course_name=self.course.name, course_price=self.course.price,
            total_price=self.course.price,
            start=timezone.now(), end=timezone.now() + timedelta(hours=1),
            status=Order.Status.DONE, payment_method=Order.PaymentMethod.PAYPAY,
        )
        mgr = self.client_as(self.manager_a)
        res = mgr.get(f"/api/op/daily-settlement/?date={date.today().isoformat()}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["settlement_status"], "OPEN")


class ShiftRequestCsvSmokeTest(RoomankOpsSmokeTestBase):
    """5. シフト申請CSV戻し承認の土台（export → preview → apply）"""

    def setUp(self):
        super().setUp()
        self.shift_request = ShiftRequest.objects.create(
            store=self.store_a, cast=self.cast_a,
            date=date.today() + timedelta(days=1),
            start_time="18:00", end_time="23:00",
        )

    def test_export_csv(self):
        mgr = self.client_as(self.manager_a)
        res = mgr.get("/api/op/shift-requests/export_csv/")
        self.assertEqual(res.status_code, 200)
        content = res.content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        self.assertTrue(any(int(r["shift_request_id"]) == self.shift_request.id for r in rows))

    def test_import_preview_and_apply(self):
        mgr = self.client_as(self.manager_a)
        target_date = (date.today() + timedelta(days=1)).isoformat()
        csv_content = (
            "shift_request_id,cast_id,approved_date,approved_start_time,approved_end_time,approved_room_id,admin_memo\n"
            f"{self.shift_request.id},{self.cast_a.id},{target_date},18:00,23:00,{self.room_shinjuku.id},スモーク承認\n"
        )
        upload = io.BytesIO(csv_content.encode("utf-8"))
        upload.name = "shift_requests.csv"

        res = mgr.post("/api/op/shift-requests/import_preview/", {"file": upload}, format="multipart")
        self.assertEqual(res.status_code, 200)
        preview = res.json()
        self.assertEqual(preview["applicable_rows"], 1)
        row = preview["rows"][0]
        self.assertTrue(row["can_apply"])
        self.assertEqual(row["errors"], [])

        res = mgr.post("/api/op/shift-requests/import_apply/", {"rows": [{
            "row_number": row["row_number"],
            "shift_request_id": row["shift_request_id"],
            "cast_id": self.cast_a.id,
            "approved_date": target_date,
            "approved_start_time": "18:00",
            "approved_end_time": "23:00",
            "approved_room_id": self.room_shinjuku.id,
            "admin_memo": "スモーク承認",
        }]}, format="json")
        self.assertEqual(res.status_code, 200)
        result = res.json()
        self.assertEqual(result["applied_count"], 1)

        self.shift_request.refresh_from_db()
        self.assertEqual(self.shift_request.status, ShiftRequest.Status.APPROVED)
        self.assertTrue(
            ShiftAssignment.objects.filter(store=self.store_a, cast=self.cast_a, date=self.shift_request.date).exists()
        )

    def test_import_preview_rejects_other_store_shift_request(self):
        other_store_request = ShiftRequest.objects.create(
            store=self.store_b, cast=self.cast_b,
            date=date.today() + timedelta(days=1), start_time="18:00", end_time="23:00",
        )
        mgr = self.client_as(self.manager_a)
        csv_content = (
            "shift_request_id,approved_date,approved_start_time,approved_end_time,approved_room_id\n"
            f"{other_store_request.id},{date.today().isoformat()},18:00,23:00,{self.room_shinjuku.id}\n"
        )
        upload = io.BytesIO(csv_content.encode("utf-8"))
        upload.name = "shift_requests.csv"
        res = mgr.post("/api/op/shift-requests/import_preview/", {"file": upload}, format="multipart")
        self.assertEqual(res.status_code, 200)
        row = res.json()["rows"][0]
        self.assertFalse(row["can_apply"])
        self.assertTrue(len(row["errors"]) > 0)

    def test_csv_endpoints_require_manager(self):
        cast_client = self.client_as(self.cast_user_a)
        res = cast_client.get("/api/op/shift-requests/export_csv/")
        self.assertEqual(res.status_code, 403)


class ExistingFeatureNotBrokenSmokeTest(RoomankOpsSmokeTestBase):
    """既存機能（CastDailyCheckout, CastAdjustment）が壊れていないことの簡易確認"""

    def test_cast_checkout_flow_still_works(self):
        cast_client = self.client_as(self.cast_user_a)
        res = cast_client.get("/api/cast/checkout/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        # Phase 6 で追加した参考値フィールドが含まれ、かつ既存フィールドも壊れていない
        self.assertIn("payment_fee_estimate", data)
        self.assertIn("net_sales_after_payment_fee", data)
        self.assertIn("done_count", data)
        self.assertTrue(data["can_submit"])

        res = cast_client.post("/api/cast/checkout/", {
            "actual_take_home_amount": 1000,
            "cast_memo": "スモークテスト退勤",
            "checklist_json": {},
        }, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertTrue(CastDailyCheckout.objects.filter(cast=self.cast_a, date=date.today()).exists())

    def test_cast_adjustment_flow_still_works(self):
        mgr = self.client_as(self.manager_a)
        res = mgr.post("/api/cast-adjustments/", {
            "cast": self.cast_a.id, "date": date.today().isoformat(),
            "amount": 500, "title": "スモークテスト調整金",
        }, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(CastAdjustment.objects.filter(cast=self.cast_a).count(), 1)

        cast_client = self.client_as(self.cast_user_a)
        res = cast_client.get("/api/cast/adjustments/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["open_total"], 500)
