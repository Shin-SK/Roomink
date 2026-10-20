from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Area, Cast, Course, Customer, Order, Room, Store, UserProfile
from core.services.sales import get_sales_dashboard, get_sales_dashboard_csv


class SalesAreaHistoryTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="エリア検証")
        self.area = Area.objects.create(store=self.store, name="新宿")
        self.other_area = Area.objects.create(store=self.store, name="六本木")
        self.room = Room.objects.create(store=self.store, name="A", area=self.area)
        self.other_room = Room.objects.create(store=self.store, name="B", area=self.other_area)
        self.cast = Cast.objects.create(store=self.store, name="検証キャスト")
        self.course = Course.objects.create(store=self.store, name="60分", duration=60, price=10000)
        self.customer = Customer.objects.create(store=self.store, phone="09000000001")
        self.start = datetime(2026, 10, 20, 15, tzinfo=ZoneInfo("Asia/Tokyo"))
        self.day = date(2026, 10, 20)
        self.manager = get_user_model().objects.create_user("area_manager")
        UserProfile.objects.create(user=self.manager, store=self.store, role=UserProfile.Role.MANAGER)
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def order(self, **overrides):
        values = dict(
            store=self.store, cast=self.cast, room=self.room, course=self.course,
            customer=self.customer, start=self.start, end=self.start + timedelta(hours=1),
            course_price=10000, options_price=2000, extension_price=3000,
            nomination_fee_price=1000, discount_amount=500, total_price=15500,
            status=Order.Status.DONE, payment_method=Order.PaymentMethod.CASH,
        )
        values.update(overrides)
        return Order.objects.create(**values)

    def dashboard(self, **filters):
        return get_sales_dashboard(self.store, self.day, self.day, **filters)

    def test_completed_order_keeps_area_after_room_move(self):
        order = self.order()
        self.room.area = self.other_area
        self.room.save()
        order.memo = "金額訂正なし"
        order.save(update_fields=["memo"])
        order.refresh_from_db()
        self.assertEqual(order.sales_area_id, self.area.id)
        self.assertEqual(self.dashboard()["by_area"][0]["area_id"], self.area.id)
        self.assertEqual(order.sales_area_logs.count(), 1)

    def test_capture_at_completion_uses_fresh_room_area(self):
        order = self.order(status=Order.Status.IN_PROGRESS)
        self.assertIsNone(order.sales_area_recorded_at)
        Room.objects.filter(pk=self.room.pk).update(area=self.other_area)
        order.status = Order.Status.DONE
        order.save(update_fields=["status"])
        order.refresh_from_db()
        self.assertEqual(order.sales_area_id, self.other_area.id)

    def test_completed_room_correction_is_audited(self):
        order = self.order()
        order.room = self.other_room
        order.updated_by = self.manager
        order.save(update_fields=["room", "updated_by"])
        order.refresh_from_db()
        self.assertEqual(order.sales_area_id, self.other_area.id)
        event = order.sales_area_logs.latest("id")
        self.assertEqual(event.before["sales_area_id"], self.area.id)
        self.assertEqual(event.after["sales_area_id"], self.other_area.id)
        self.assertEqual(event.acted_by, self.manager)

    def test_partial_save_does_not_capture_unsaved_status_or_room(self):
        order = self.order(status=Order.Status.CONFIRMED)
        order.status = Order.Status.DONE
        order.save(update_fields=["memo"])
        order.refresh_from_db()
        self.assertIsNone(order.sales_area_recorded_at)
        order.status = Order.Status.DONE
        order.room = self.other_room
        order.save(update_fields=["status"])
        order.refresh_from_db()
        self.assertEqual(order.sales_area_id, self.area.id)

    def test_legacy_order_is_not_backfilled_by_read_or_unrelated_edit(self):
        order = self.order()
        Order.objects.filter(pk=order.pk).update(sales_area=None, sales_area_recorded_at=None)
        order.refresh_from_db()
        order.memo = "過去分"
        order.save()
        self.assertIsNone(Order.objects.get(pk=order.pk).sales_area_recorded_at)
        self.assertEqual(self.dashboard()["by_area"][0]["area_name"], "未設定")

    def test_unassigned_and_roomless_orders_are_in_totals(self):
        self.order()
        self.order(room=None)
        self.order(room=Room.objects.create(store=self.store, name="未設定ルーム"))
        self.order(status=Order.Status.CANCELLED)
        self.order(status=Order.Status.CONFIRMED)
        result = self.dashboard()
        unknown = next(row for row in result["by_area"] if row["area_id"] is None)
        self.assertEqual(unknown["orders"], 2)
        for total, column in [("total_orders", "orders"), ("total_sales", "sales"),
                              ("course_sales", "course_sales"), ("options_sales", "options_sales"),
                              ("extension_sales", "extension_sales"),
                              ("nomination_fee_sales", "nomination_fee_sales"),
                              ("discount_amount", "discount_amount")]:
            self.assertEqual(result[total], sum(row[column] for row in result["by_area"]))

    def test_new_room_only_adds_new_sales(self):
        self.order()
        new_room = Room.objects.create(store=self.store, name="追加", area=self.other_area)
        self.assertEqual(len(self.dashboard()["by_area"]), 1)
        self.order(room=new_room)
        self.assertEqual(len(self.dashboard()["by_area"]), 2)

    def test_snapshot_cannot_be_overwritten_by_normal_save(self):
        order = self.order()
        order.sales_area = self.other_area
        order.save(update_fields=["sales_area"])
        order.refresh_from_db()
        self.assertEqual(order.sales_area_id, self.area.id)

    def test_rename_and_retirement_preserve_area_identity(self):
        self.order()
        self.room.area = self.other_area
        self.room.save()
        self.area.name = "新宿エリア"
        self.area.is_active = False
        self.area.save()
        self.assertEqual(self.dashboard()["by_area"][0]["area_name"], "新宿エリア")
        with self.assertRaises(ProtectedError):
            self.area.delete()
        response = self.client.delete(f"/api/areas/{self.area.id}/")
        self.assertEqual(response.status_code, 409)

    def test_dashboard_and_export_reject_staff_and_other_store_is_isolated(self):
        self.order()
        response = self.client.get("/api/op/sales-dashboard/?date_from=2026-10-20&date_to=2026-10-20")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["by_area"][0]["area_id"], self.area.id)
        staff = get_user_model().objects.create_user("area_staff")
        UserProfile.objects.create(user=staff, store=self.store, role=UserProfile.Role.STAFF)
        self.client.force_authenticate(staff)
        for path in ("sales-dashboard/", "sales-dashboard-export.csv"):
            self.assertEqual(self.client.get(f"/api/op/{path}?range=month").status_code, 403)
        other_manager = get_user_model().objects.create_user("other_area_manager")
        UserProfile.objects.create(user=other_manager, store=Store.objects.create(name="別店舗"), role=UserProfile.Role.MANAGER)
        self.client.force_authenticate(other_manager)
        response = self.client.get("/api/op/sales-dashboard/?date_from=2026-10-20&date_to=2026-10-20")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["by_area"], [])

    def test_csv_matches_area_values_and_is_read_only(self):
        order = self.order()
        before = Order.objects.values().get(pk=order.pk)
        csv_text = get_sales_dashboard_csv(self.store, self.day, self.day)
        self.assertIn("新宿,1,15500,10000,2000,3000,1000,500", csv_text)
        self.assertEqual(Order.objects.values().get(pk=order.pk), before)

    def test_filters_use_same_orders_for_area_and_total(self):
        self.order()
        self.order(room=self.other_room, payment_method=Order.PaymentMethod.CARD)
        result = self.dashboard(room_id=self.room.id, payment_method=Order.PaymentMethod.CASH)
        self.assertEqual(result["total_orders"], 1)
        self.assertEqual(sum(row["sales"] for row in result["by_area"]), result["total_sales"])

    def test_audit_failure_rolls_back_completion_and_snapshot(self):
        order = self.order(status=Order.Status.PENDING_FINALIZE)
        with patch("core.models.OrderSalesAreaLog.objects.create", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                order.status = Order.Status.DONE
                order.save(update_fields=["status"])
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING_FINALIZE)
        self.assertIsNone(order.sales_area_recorded_at)

    def test_manager_completion_endpoint_records_area_and_repeat_does_not_duplicate(self):
        order = self.order(status=Order.Status.PENDING_FINALIZE)
        path = f"/api/orders/{order.pk}/done/"
        self.assertEqual(self.client.post(path).status_code, 200)
        self.assertEqual(self.client.post(path).status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.sales_area_id, self.area.pk)
        self.assertEqual(order.sales_area_logs.count(), 1)

    def test_cast_completion_endpoint_records_area(self):
        user = get_user_model().objects.create_user("area_cast")
        UserProfile.objects.create(user=user, store=self.store, role=UserProfile.Role.CAST)
        self.cast.user = user
        self.cast.save()
        order = self.order(status=Order.Status.IN_PROGRESS)
        self.client.force_authenticate(user)
        response = self.client.post(f"/api/cast/orders/{order.pk}/complete/")
        self.assertEqual(response.status_code, 200, response.data)
        order.refresh_from_db()
        self.assertEqual(order.sales_area_id, self.area.pk)
