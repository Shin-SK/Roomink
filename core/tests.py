"""
Roomink Ops スモークテスト（Django test client / DRF APIClient ベース）。

今回追加した5機能を中心に、以下を確認する:
  1. エリアタグ付き売上集計（Room.area_name → /op/sales-dashboard/ の by_area）
  2. ノート/施術マニュアル（CastNote CRUD・cast側閲覧・store分離）
  3. 出勤確認の外部通知の土台（ShiftConfirmNotificationLog・テストログ作成・実送信なし）
  4. PayPay/カード手数料の精算反映（Order.PaymentMethod.PAYPAY・手数料設定・sales-dashboardの手数料見込み）
  5. シフト申請CSV戻し承認の土台（export_csv → import_preview → import_apply、既存承認ロジック再利用）

今回追加した4機能（WeeklyShiftSmokeTest 以降）:
  6. 週次シフト入力（/op/shifts/weekly/）
  7. SMS文面設定（/op/sms-templates/・支払方法別テンプレート）
  8. 予約ごとのSMS送信履歴（/op/orders/<id>/sms-logs/）
  9. タイムラインの出勤セラピスト並び替え（/op/schedule-cast-order/）

既存機能（DailySettlementView, CastDailyCheckout, CastAdjustment, Order の基本挙動）を壊していないことも
あわせて確認する。外部API送信・本番DB操作は一切行わない（テストはDjangoのテスト用DBのみを使用する）。

実行方法:
    python3 manage.py test core
"""
import csv
import io
from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import (
    Cast, CastAdjustment, CastDailyCheckout, CastNote, Course, Customer,
    Order, Room, ShiftAssignment, ShiftConfirmNotificationLog, ShiftRequest,
    SmsTemplate, Store, UserProfile,
)
from core.services.notify import build_confirmation_body

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


# ──────────────────────────────────────
# 6〜9. 週次シフト入力 / SMS文面設定 / SMS送信履歴 / タイムライン並び替え
#   外部SMS実送信は行わない（Twilio環境変数が無い場合はダミー送信＋SmsLog記録のみ）
# ──────────────────────────────────────

class WeeklyShiftAndSmsSmokeTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="S1")
        self.other = Store.objects.create(name="S2")
        self.room = Room.objects.create(store=self.store, name="R1")
        self.other_room = Room.objects.create(store=self.other, name="R2")
        self.cast = Cast.objects.create(store=self.store, name="C1")
        self.other_cast = Cast.objects.create(store=self.other, name="C2")

        self.mgr = User.objects.create_user("mgr", password="x")
        UserProfile.objects.create(user=self.mgr, store=self.store, role="manager")
        self.cast_user = User.objects.create_user("castu", password="x")
        UserProfile.objects.create(user=self.cast_user, store=self.store, role="cast")

        self.client = APIClient()
        self.client.force_authenticate(self.mgr)
        self.week = date(2026, 7, 13)  # 月曜

    # 1. 週次シフト入力
    def test_weekly_create(self):
        res = self.client.post("/api/op/shifts/weekly/", {
            "cast": self.cast.id,
            "week_start": self.week.isoformat(),
            "items": [
                {"date": "2026-07-13", "enabled": True, "start_time": "18:00",
                 "end_time": "23:00", "room": self.room.id},
                {"date": "2026-07-14", "enabled": False},
                {"date": "2026-07-15", "enabled": True, "start_time": "18:00",
                 "end_time": "23:00", "room": self.room.id},
            ],
        }, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["created_count"], 2)
        self.assertEqual(ShiftAssignment.objects.filter(store=self.store).count(), 2)

    def test_weekly_conflict_is_all_or_nothing(self):
        ShiftAssignment.objects.create(
            store=self.store, date=date(2026, 7, 13), cast=self.cast,
            room=self.room, start_time=time(18, 0), end_time=time(23, 0),
        )
        res = self.client.post("/api/op/shifts/weekly/", {
            "cast": self.cast.id,
            "week_start": self.week.isoformat(),
            "items": [
                {"date": "2026-07-13", "enabled": True, "start_time": "19:00",
                 "end_time": "22:00", "room": self.room.id},
                {"date": "2026-07-14", "enabled": True, "start_time": "18:00",
                 "end_time": "23:00", "room": self.room.id},
            ],
        }, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertTrue(res.data["errors"])
        # 1件も登録されない
        self.assertEqual(ShiftAssignment.objects.filter(store=self.store).count(), 1)

    def test_weekly_rejects_other_store_room(self):
        res = self.client.post("/api/op/shifts/weekly/", {
            "cast": self.cast.id,
            "week_start": self.week.isoformat(),
            "items": [{"date": "2026-07-13", "enabled": True, "start_time": "18:00",
                       "end_time": "23:00", "room": self.other_room.id}],
        }, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(ShiftAssignment.objects.count(), 0)

    def test_weekly_rejects_other_store_cast(self):
        res = self.client.post("/api/op/shifts/weekly/", {
            "cast": self.other_cast.id,
            "week_start": self.week.isoformat(),
            "items": [{"date": "2026-07-13", "enabled": True, "start_time": "18:00",
                       "end_time": "23:00", "room": self.room.id}],
        }, format="json")
        self.assertEqual(res.status_code, 404)

    def test_weekly_forbidden_for_cast_role(self):
        self.client.force_authenticate(self.cast_user)
        res = self.client.get(f"/api/op/shifts/weekly/?cast={self.cast.id}&week_start={self.week}")
        self.assertEqual(res.status_code, 403)

    # 4. 並び替え
    def test_cast_order_roundtrip(self):
        c2 = Cast.objects.create(store=self.store, name="AAA")
        s1 = ShiftAssignment.objects.create(
            store=self.store, date=self.week, cast=self.cast, room=self.room,
            start_time=time(18, 0), end_time=time(23, 0))
        s2 = ShiftAssignment.objects.create(
            store=self.store, date=self.week, cast=c2, room=self.room,
            start_time=time(18, 0), end_time=time(23, 0))

        res = self.client.post("/api/op/schedule-cast-order/", {
            "date": self.week.isoformat(),
            "items": [
                {"shift_assignment_id": s1.id, "display_order": 1},
                {"shift_assignment_id": s2.id, "display_order": 2},
            ],
        }, format="json")
        self.assertEqual(res.status_code, 200, res.data)

        # タイムラインが display_order 順（名前順 AAA が先ではなくなる）
        sched = self.client.get(f"/api/op/schedule/?date={self.week}")
        names = [c["name"] for c in sched.data["casts"]]
        self.assertEqual(names, ["C1", "AAA"])

        # シフト時間・部屋は不変
        s1.refresh_from_db()
        self.assertEqual(s1.start_time, time(18, 0))
        self.assertEqual(s1.room_id, self.room.id)

    def test_cast_order_rejects_other_store_shift(self):
        foreign = ShiftAssignment.objects.create(
            store=self.other, date=self.week, cast=self.other_cast,
            room=self.other_room, start_time=time(18, 0), end_time=time(23, 0))
        res = self.client.post("/api/op/schedule-cast-order/", {
            "date": self.week.isoformat(),
            "items": [{"shift_assignment_id": foreign.id, "display_order": 1}],
        }, format="json")
        self.assertEqual(res.status_code, 400)
        foreign.refresh_from_db()
        self.assertEqual(foreign.display_order, 0)

    # 2 & 3. SMS
    def _make_order(self, pm=Order.PaymentMethod.CASH):
        cu = Customer.objects.create(store=self.store, display_name="山田", phone="09012345678")
        course = Course.objects.create(store=self.store, name="60分", duration=60, price=10000)
        from django.utils import timezone
        start = timezone.now()
        return Order.objects.create(
            store=self.store, cast=self.cast, room=self.room, customer=cu,
            course=course, course_name="60分", course_price=10000, total_price=10000,
            start=start, end=start + timedelta(minutes=60),
            status=Order.Status.REQUESTED, payment_method=pm,
        )

    def test_sms_template_used_when_active(self):
        order = self._make_order(Order.PaymentMethod.PAYPAY)
        SmsTemplate.objects.create(
            store=self.store,
            template_type=SmsTemplate.TemplateType.RESERVATION_CONFIRMATION,
            payment_method=Order.PaymentMethod.PAYPAY,
            body="{customer_name}様 PayPay {total_price}円 {course_name}",
            is_active=True,
        )
        body = build_confirmation_body(order)
        self.assertEqual(body, "山田様 PayPay 10,000円 60分")

    def test_sms_default_used_when_no_template(self):
        order = self._make_order(Order.PaymentMethod.CASH)
        body = build_confirmation_body(order)
        self.assertIn("現金でのお支払い", body)

    def test_sms_inactive_template_falls_back(self):
        order = self._make_order(Order.PaymentMethod.CASH)
        SmsTemplate.objects.create(
            store=self.store,
            template_type=SmsTemplate.TemplateType.RESERVATION_CONFIRMATION,
            payment_method=Order.PaymentMethod.CASH,
            body="使わない文面", is_active=False,
        )
        self.assertIn("現金でのお支払い", build_confirmation_body(order))

    def test_confirm_creates_sms_log_and_detail_api(self):
        order = self._make_order(Order.PaymentMethod.CARD)
        res = self.client.post(f"/api/orders/{order.id}/confirm/")
        self.assertEqual(res.status_code, 200, res.data)

        logs = self.client.get(f"/api/op/orders/{order.id}/sms-logs/")
        self.assertEqual(logs.status_code, 200)
        kinds = {l["template_type"]: l for l in logs.data}
        self.assertIn("RESERVATION_CONFIRMATION", kinds)
        confirm_log = kinds["RESERVATION_CONFIRMATION"]
        self.assertEqual(confirm_log["status"], "SENT")
        self.assertEqual(confirm_log["to_phone"], "09012345678")
        self.assertEqual(confirm_log["payment_method"], "CARD")
        self.assertTrue(confirm_log["sent_at"])
        # キャスト通知は電話番号が無いので SKIPPED
        self.assertEqual(kinds["CAST_NOTICE"]["status"], "SKIPPED")

    def test_sms_logs_other_store_404(self):
        order = self._make_order()
        other_user = User.objects.create_user("o", password="x")
        UserProfile.objects.create(user=other_user, store=self.other, role="manager")
        self.client.force_authenticate(other_user)
        res = self.client.get(f"/api/op/orders/{order.id}/sms-logs/")
        self.assertEqual(res.status_code, 404)

    def test_sms_templates_put_manager_and_staff_readonly(self):
        res = self.client.put("/api/op/sms-templates/", {
            "items": [{"payment_method": "CASH", "body": "現金文面", "is_active": True}],
        }, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(len(res.data["items"]), 4)

        staff = User.objects.create_user("st", password="x")
        UserProfile.objects.create(user=staff, store=self.store, role="staff")
        self.client.force_authenticate(staff)
        self.assertEqual(self.client.get("/api/op/sms-templates/").status_code, 200)
        self.assertEqual(self.client.put("/api/op/sms-templates/", {"items": []}, format="json").status_code, 403)

    def test_sms_templates_store_scoped(self):
        SmsTemplate.objects.create(
            store=self.other,
            template_type=SmsTemplate.TemplateType.RESERVATION_CONFIRMATION,
            payment_method=Order.PaymentMethod.CASH, body="他店舗", is_active=True)
        res = self.client.get("/api/op/sms-templates/")
        bodies = [i["body"] for i in res.data["items"]]
        self.assertNotIn("他店舗", bodies)
