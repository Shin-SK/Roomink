"""起動前の収益・店舗境界・通知経路の回帰テスト。"""

from datetime import date, datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    Cast,
    CastExpense,
    Course,
    Customer,
    DailySettlement,
    Option,
    Order,
    PointLog,
    Room,
    ShiftAssignment,
    Store,
    UserProfile,
)


User = get_user_model()


class PrelaunchIntegrityTest(TestCase):
    def setUp(self):
        self.day = date(2031, 1, 10)
        self.start = timezone.make_aware(datetime(2031, 1, 10, 12, 0))
        self.store = Store.objects.create(name="境界テスト店A")
        self.other_store = Store.objects.create(name="境界テスト店B")
        self.manager = User.objects.create_user("integrity-manager")
        UserProfile.objects.create(
            user=self.manager,
            store=self.store,
            role=UserProfile.Role.MANAGER,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

        self.cast = Cast.objects.create(store=self.store, name="キャストA")
        self.other_cast = Cast.objects.create(store=self.other_store, name="キャストB")
        self.room = Room.objects.create(store=self.store, name="A-101")
        self.course = Course.objects.create(store=self.store, name="Aコース", duration=60, price=10000)
        self.other_course = Course.objects.create(store=self.other_store, name="Bコース", duration=60, price=10000)
        self.option = Option.objects.create(store=self.store, name="Aオプション", price=1000)
        self.other_option = Option.objects.create(store=self.other_store, name="Bオプション", price=1000)
        self.customer = Customer.objects.create(store=self.store, display_name="顧客A", phone="09000000001")
        ShiftAssignment.objects.create(
            store=self.store,
            date=self.day,
            cast=self.cast,
            room=self.room,
            start_time=time(10, 0),
            end_time=time(18, 0),
        )

    def order_payload(self, **overrides):
        payload = {
            "customer": self.customer.id,
            "cast": self.cast.id,
            "course": self.course.id,
            "start": self.start.isoformat(),
        }
        payload.update(overrides)
        return payload

    def create_order(self, **overrides):
        response = self.client.post("/api/orders/", self.order_payload(**overrides), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return Order.objects.get(pk=response.data["id"])

    def test_order_api_rejects_foreign_cast_course_and_option(self):
        for field, value in (
            ("cast", self.other_cast.id),
            ("course", self.other_course.id),
            ("options", [self.other_option.id]),
        ):
            with self.subTest(field=field):
                response = self.client.post(
                    "/api/orders/",
                    self.order_payload(**{field: value}),
                    format="json",
                )
                self.assertEqual(response.status_code, 400, response.data)
                self.assertEqual(Order.objects.count(), 0)

    def test_model_rejects_cross_store_order_outside_api(self):
        with self.assertRaises(ValidationError):
            Order.objects.create(
                store=self.store,
                cast=self.other_cast,
                room=self.room,
                customer=self.customer,
                course=self.course,
                start=self.start,
                end=self.start + timedelta(hours=1),
            )

    def test_locked_day_blocks_financial_records(self):
        DailySettlement.objects.create(
            store=self.store,
            date=self.day,
            status=DailySettlement.Status.LOCKED,
            snapshot_json={"rows": [], "totals": {}},
        )
        point = self.client.post(
            "/api/point-logs/",
            {"cast": self.cast.id, "date": self.day.isoformat(), "points": 10},
            format="json",
        )
        expense = self.client.post(
            "/api/cast-expenses/",
            {"cast": self.cast.id, "date": self.day.isoformat(), "name": "交通費", "amount": 1000},
            format="json",
        )
        self.assertEqual(point.status_code, 400, point.data)
        self.assertEqual(expense.status_code, 400, expense.data)
        self.assertFalse(PointLog.objects.exists())
        self.assertFalse(CastExpense.objects.exists())

    def test_card_order_cannot_be_counted_as_done_before_confirmation(self):
        order = self.create_order()
        order.status = Order.Status.PENDING_FINALIZE
        order.payment_method = Order.PaymentMethod.CARD
        order.save(update_fields=["status", "payment_method", "updated_at"])

        response = self.client.post(f"/api/orders/{order.id}/done/", format="json")

        self.assertEqual(response.status_code, 400, response.data)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING_FINALIZE)


class LineCredentialExposureTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="LINE秘密情報テスト店",
            line_is_enabled=True,
            line_channel_secret="do-not-return-me",
            line_channel_access_token="do-not-return-me-either",
        )
        self.admin = User.objects.create_superuser("integrity-admin")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        session = self.client.session
        session["platform_store_id"] = self.store.id
        session.save()

    def test_settings_never_returns_line_credentials(self):
        response = self.client.get("/api/op/line-settings/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn("line_channel_secret", response.data)
        self.assertNotIn("line_channel_access_token", response.data)
        self.assertTrue(response.data["line_channel_secret_configured"])
        self.assertTrue(response.data["line_channel_access_token_configured"])

    def test_webhook_without_secret_fails_closed(self):
        self.store.line_channel_secret = ""
        self.store.save(update_fields=["line_channel_secret"])

        response = APIClient().post(
            f"/api/webhook/line/{self.store.line_webhook_token}/",
            {"events": []},
            format="json",
        )

        self.assertEqual(response.status_code, 503, response.data)
