from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    Cast,
    CastNote,
    Course,
    Customer,
    NominationFee,
    Option,
    Order,
    SmsLog,
    SmsTemplate,
    Store,
    UserProfile,
)
from core.services.notify import build_confirmation_body


User = get_user_model()


@override_settings(FRONTEND_URL="https://roomink.example", PUBLIC_BOOKING_ENABLED=True)
class ClientFollowupUpdatesTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="アールズスパ",
            slug="followup-rs-spa",
            public_booking_notice="●割引名は備考欄へご入力ください。",
        )
        self.other_store = Store.objects.create(name="東京メンズエステ", slug="followup-tokyo-mens-esthe")
        self.manager = self._user("followup_manager", self.store, UserProfile.Role.MANAGER)
        self.staff = self._user("followup_staff", self.store, UserProfile.Role.STAFF)
        self.cast_user = self._user("followup_cast", self.store, UserProfile.Role.CAST)
        self.other_cast_user = self._user("followup_other_cast", self.store, UserProfile.Role.CAST)
        self.cast = Cast.objects.create(store=self.store, user=self.cast_user, name="対象キャスト")
        self.other_cast = Cast.objects.create(
            store=self.store,
            user=self.other_cast_user,
            name="対象外キャスト",
        )
        self.foreign_cast = Cast.objects.create(store=self.other_store, name="別店舗キャスト")
        self.customer = Customer.objects.create(
            store=self.store,
            display_name="予約顧客",
            phone="09011112222",
        )
        self.course = Course.objects.create(
            store=self.store,
            name="120分コース",
            duration=120,
            price=20000,
        )

    def _user(self, username, store, role):
        user = User.objects.create_user(username, password="pass")
        UserProfile.objects.create(user=user, store=store, role=role)
        return user

    def _client(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_sms_discount_placeholders_render_from_order_snapshot(self):
        order = Order.objects.create(
            store=self.store,
            cast=self.cast,
            customer=self.customer,
            course=self.course,
            course_name=self.course.name,
            course_price=20000,
            discount_name="初回割引",
            discount_amount=2000,
            total_price=18000,
            start=timezone.now() + timedelta(days=1),
            end=timezone.now() + timedelta(days=1, hours=2),
            status=Order.Status.CONFIRMED,
        )
        SmsTemplate.objects.create(
            store=self.store,
            payment_method=Order.PaymentMethod.UNSET,
            body=(
                "{discount_name}:{discount_amount}円\n"
                "割引前:{subtotal_price}円\n合計:{total_price}円"
            ),
            is_active=True,
        )

        body = build_confirmation_body(order)

        self.assertIn("初回割引:2,000円", body)
        self.assertIn("割引前:20,000円", body)
        self.assertIn("合計:18,000円", body)

    def test_sms_booking_detail_placeholders_render_from_order_snapshot(self):
        nomination_fee = NominationFee.objects.create(
            store=self.store,
            name="本指名",
            price=3000,
        )
        option = Option.objects.create(
            store=self.store,
            name="衣装チェンジ",
            price=2000,
        )
        order = Order.objects.create(
            store=self.store,
            cast=self.cast,
            customer=self.customer,
            course=self.course,
            course_name=self.course.name,
            course_price=20000,
            options_price=2000,
            nomination_fee=nomination_fee,
            nomination_fee_name=nomination_fee.name,
            nomination_fee_price=nomination_fee.price,
            total_price=25000,
            start=timezone.now() + timedelta(days=1),
            end=timezone.now() + timedelta(days=1, hours=2),
            status=Order.Status.CONFIRMED,
        )
        order.options.add(option)
        SmsTemplate.objects.create(
            store=self.store,
            payment_method=Order.PaymentMethod.UNSET,
            body=(
                "指名:{nomination_type} {nomination_price}円\n"
                "コース:{course_price}円\n"
                "オプション:{option_names} {option_price}円"
            ),
            is_active=True,
        )

        body = build_confirmation_body(order)

        self.assertIn("指名:本指名 3,000円", body)
        self.assertIn("コース:20,000円", body)
        self.assertIn("オプション:衣装チェンジ 2,000円", body)

    def test_sms_preview_renders_without_sending_or_writing(self):
        client = self._client(self.manager)
        before_templates = SmsTemplate.objects.count()
        before_logs = SmsLog.objects.count()

        response = client.post(
            "/api/op/sms-templates/",
            {
                "payment_method": Order.PaymentMethod.CASH,
                "scenario": "discount",
                "body": (
                    "{customer_name}様 {discount_name} -{discount_amount}円 合計{total_price}円\n"
                    "{nomination_type} {nomination_price}円／{course_price}円\n"
                    "{option_names} {option_price}円"
                ),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["sent"], False)
        self.assertEqual(response.data["unresolved_placeholders"], [])
        self.assertIn("山田太郎様 初回割引 -2,000円 合計18,000円", response.data["rendered_body"])
        self.assertIn("本指名 3,000円／15,000円", response.data["rendered_body"])
        self.assertIn("衣装チェンジ、延長オプション 2,000円", response.data["rendered_body"])
        self.assertEqual(SmsTemplate.objects.count(), before_templates)
        self.assertEqual(SmsLog.objects.count(), before_logs)

    def test_store_booking_notice_and_dedicated_url_are_store_scoped(self):
        manager_client = self._client(self.manager)
        staff_client = self._client(self.staff)

        get_response = manager_client.get("/api/op/public-booking-settings/")
        patch_response = manager_client.patch(
            "/api/op/public-booking-settings/",
            {"public_booking_notice": "●SMSが届かない場合は店舗へご連絡ください。"},
            format="json",
        )
        forbidden_response = staff_client.patch(
            "/api/op/public-booking-settings/",
            {"public_booking_notice": "変更不可"},
            format="json",
        )
        public_response = APIClient().get(
            "/api/public/booking/options/",
            {"store": self.store.pk},
        )

        self.assertEqual(get_response.status_code, 200, get_response.data)
        self.assertEqual(
            get_response.data["public_booking_url"],
            "https://roomink.example/s/followup-rs-spa/booking",
        )
        self.assertEqual(patch_response.status_code, 200, patch_response.data)
        self.assertEqual(forbidden_response.status_code, 403, forbidden_response.data)
        self.assertEqual(public_response.status_code, 200, public_response.data)
        self.assertEqual(
            public_response.data["store"]["public_booking_notice"],
            "●SMSが届かない場合は店舗へご連絡ください。",
        )
        self.other_store.refresh_from_db()
        self.assertEqual(self.other_store.public_booking_notice, "")

    def test_note_targets_and_images_are_only_returned_to_selected_cast(self):
        note = CastNote.objects.create(
            store=self.store,
            title="対象者限定ノート",
            body="画像を確認してください。",
            status=CastNote.Status.PUBLISHED,
            visibility=CastNote.Visibility.CAST,
            image_urls=["https://res.cloudinary.com/example/image/upload/note.jpg"],
        )
        note.target_casts.add(self.cast)

        visible = self._client(self.cast_user).get("/api/cast/notes/")
        hidden = self._client(self.other_cast_user).get("/api/cast/notes/")

        self.assertEqual(visible.status_code, 200, visible.data)
        self.assertEqual([item["id"] for item in visible.data["recent"]], [note.id])
        self.assertEqual(visible.data["recent"][0]["image_urls"], note.image_urls)
        self.assertEqual(hidden.status_code, 200, hidden.data)
        self.assertEqual(hidden.data["recent"], [])

    def test_note_keeps_inline_image_marker_between_text_sections(self):
        image_url = "https://res.cloudinary.com/example/image/upload/note-inline.jpg"
        body = "入口のご案内\n[[画像1]]\nドアの位置をご確認ください。"
        response = self._client(self.manager).post(
            "/api/cast-notes/",
            {
                "title": "画像付き案内",
                "body": body,
                "visibility": CastNote.Visibility.CAST,
                "status": CastNote.Status.PUBLISHED,
                "image_urls": [image_url],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        visible = self._client(self.cast_user).get("/api/cast/notes/")
        note = next(item for item in visible.data["recent"] if item["id"] == response.data["id"])
        self.assertEqual(note["body"], body)
        self.assertEqual(note["image_urls"], [image_url])

    def test_manager_cannot_target_cast_from_another_store(self):
        response = self._client(self.manager).post(
            "/api/cast-notes/",
            {
                "title": "不正な対象指定",
                "visibility": CastNote.Visibility.CAST,
                "target_cast_ids": [self.foreign_cast.pk],
                "image_urls": [],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(CastNote.objects.filter(title="不正な対象指定").exists())
