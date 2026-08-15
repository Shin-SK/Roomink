from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Cast, Course, Customer, Order, Room, SmsTemplate, Store, UserProfile
from core.services.notify import build_confirmation_body


User = get_user_model()


class RoomSmsGuidanceTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="SMSルーム案内テスト店舗")
        self.manager = User.objects.create_user("sms_room_manager", password="pass")
        UserProfile.objects.create(
            user=self.manager,
            store=self.store,
            role=UserProfile.Role.MANAGER,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

        self.room = Room.objects.create(
            store=self.store,
            name="中央区銀座ルーム",
            address="東京都中央区銀座2-14-15 2000銀座コーポ305号室",
            map_url="https://maps.google.com/?q=中央区銀座2-14-15",
            sms_notice="似た建物が多いため、建物名で検索してください。",
        )
        self.cast = Cast.objects.create(store=self.store, name="テストセラピスト")
        self.customer = Customer.objects.create(
            store=self.store,
            display_name="予約顧客",
            phone="09011112222",
        )
        self.course = Course.objects.create(
            store=self.store,
            name="100分",
            duration=100,
            price=20000,
        )

    def make_order(self, room=None):
        start = timezone.now() + timedelta(days=1)
        return Order.objects.create(
            store=self.store,
            cast=self.cast,
            room=room,
            customer=self.customer,
            course=self.course,
            course_name=self.course.name,
            course_price=self.course.price,
            total_price=self.course.price,
            start=start,
            end=start + timedelta(minutes=self.course.duration),
            status=Order.Status.CONFIRMED,
            payment_method=Order.PaymentMethod.CASH,
        )

    def test_manager_can_save_room_map_url_and_sms_notice(self):
        response = self.client.patch(
            f"/api/rooms/{self.room.id}/",
            {
                "map_url": "https://maps.app.goo.gl/example",
                "sms_notice": "入口を間違えやすいためご注意ください。",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["map_url"], "https://maps.app.goo.gl/example")
        self.assertEqual(response.data["sms_notice"], "入口を間違えやすいためご注意ください。")

    def test_active_template_renders_room_guidance(self):
        order = self.make_order(room=self.room)
        SmsTemplate.objects.create(
            store=self.store,
            payment_method=Order.PaymentMethod.CASH,
            body=(
                "ルーム:{room_name}\n住所:{room_address}\n"
                "地図:{room_map_url}\n注意:{room_notice}"
            ),
            is_active=True,
        )

        body = build_confirmation_body(order)

        self.assertIn("ルーム:中央区銀座ルーム", body)
        self.assertIn("住所:東京都中央区銀座2-14-15 2000銀座コーポ305号室", body)
        self.assertIn("地図:https://maps.google.com/?q=中央区銀座2-14-15", body)
        self.assertIn("注意:似た建物が多いため、建物名で検索してください。", body)

    def test_default_body_includes_available_room_guidance(self):
        body = build_confirmation_body(self.make_order(room=self.room))

        self.assertIn("ルーム: 中央区銀座ルーム", body)
        self.assertIn("住所: 東京都中央区銀座2-14-15 2000銀座コーポ305号室", body)
        self.assertIn("地図: https://maps.google.com/?q=中央区銀座2-14-15", body)
        self.assertIn("※似た建物が多いため、建物名で検索してください。", body)

    def test_room_pending_does_not_include_address_map_or_notice(self):
        body = build_confirmation_body(self.make_order(room=None))

        self.assertIn("ルーム: 調整中", body)
        self.assertNotIn(self.room.address, body)
        self.assertNotIn(self.room.map_url, body)
        self.assertNotIn(self.room.sms_notice, body)

    def test_sms_template_settings_exposes_room_placeholders(self):
        response = self.client.get("/api/op/sms-templates/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn("room_address", response.data["placeholders"])
        self.assertIn("room_map_url", response.data["placeholders"])
        self.assertIn("room_notice", response.data["placeholders"])
