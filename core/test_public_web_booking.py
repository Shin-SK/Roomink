from datetime import date, datetime, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth.hashers import check_password
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import (
    Cast,
    Course,
    Customer,
    CustomerAccountInvitation,
    Option,
    Order,
    PublicBookingVerification,
    Room,
    ShiftAssignment,
    SmsLog,
    Store,
)


TOKYO = ZoneInfo("Asia/Tokyo")


@override_settings(
    FRONTEND_URL="https://roomink.example",
    SMS_DUMMY_MODE=True,
    PUBLIC_BOOKING_ENABLED=True,
)
class PublicWebBookingTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.business_date = date(2030, 1, 15)
        self.store = Store.objects.create(name="公開予約店舗", timezone="Asia/Tokyo")
        self.other_store = Store.objects.create(name="他店舗", timezone="Asia/Tokyo")
        self.cast = Cast.objects.create(
            store=self.store,
            name="公開予約キャスト",
            interval_minutes=15,
        )
        self.room = Room.objects.create(
            store=self.store,
            name="101",
            address="東京都新宿区テスト1-2-3",
            area_name="新宿",
        )
        self.course = Course.objects.create(
            store=self.store,
            name="120分コース",
            duration=120,
            price=20000,
        )
        self.option = Option.objects.create(
            store=self.store,
            name="テストオプション",
            price=2000,
        )
        self.other_option = Option.objects.create(
            store=self.other_store,
            name="他店舗オプション",
            price=9999,
        )
        ShiftAssignment.objects.create(
            store=self.store,
            date=self.business_date,
            cast=self.cast,
            room=self.room,
            start_time=time(12, 0),
            end_time=time(15, 0),
        )

    def payload(self, **overrides):
        data = {
            "store": self.store.id,
            "display_name": "公開予約 太郎",
            "phone": "090-1234-5678",
            "cast": self.cast.id,
            "course": self.course.id,
            "date": self.business_date.isoformat(),
            "start": datetime(2030, 1, 15, 12, 30, tzinfo=TOKYO).isoformat(),
            "options": [self.option.id],
            "memo": "Web予約テスト",
        }
        data.update(overrides)
        return data

    def request_code(self, **overrides):
        with patch(
            "core.services.public_booking.generate_public_booking_code",
            return_value="123456",
        ):
            return self.client.post(
                "/api/public/booking/request-verification/",
                self.payload(**overrides),
                format="json",
            )

    def test_anonymous_can_load_options_and_course_length_aware_slots(self):
        Cast.objects.create(store=self.store, name="別日出勤キャスト")
        options = self.client.get(
            "/api/public/booking/options/",
            {"store": self.store.id, "date": self.business_date.isoformat()},
        )
        slots = self.client.get(
            "/api/public/booking/slots/",
            {
                "store": self.store.id,
                "cast": self.cast.id,
                "course": self.course.id,
                "date": self.business_date.isoformat(),
            },
        )

        self.assertEqual(options.status_code, 200, options.data)
        self.assertEqual(options.data["store"]["name"], self.store.name)
        self.assertEqual([item["id"] for item in options.data["casts"]], [self.cast.id])
        self.assertEqual(options.data["casts"][0]["id"], self.cast.id)
        self.assertEqual(options.data["casts"][0]["area_names"], ["新宿"])
        self.assertEqual(options.data["casts"][0]["shift_summaries"][0], {
            "room_name": "101",
            "area_name": "新宿",
            "start": "12:00",
            "end": "15:00",
        })
        self.assertEqual(slots.status_code, 200, slots.data)
        starts = [slot["start"] for slot in slots.data["slots"]]
        self.assertEqual(starts, ["12:00", "12:30", "13:00"])
        self.assertEqual(slots.data["slots"][0]["end"], "14:00")

    @override_settings(PUBLIC_BOOKING_ENABLED=False)
    def test_disabled_public_booking_is_fail_closed(self):
        options = self.client.get(
            "/api/public/booking/options/",
            {"store": self.store.id},
        )
        requested = self.client.post(
            "/api/public/booking/request-verification/",
            self.payload(),
            format="json",
        )

        self.assertEqual(options.status_code, 503, options.data)
        self.assertEqual(requested.status_code, 503, requested.data)
        self.assertEqual(PublicBookingVerification.objects.count(), 0)
        self.assertEqual(SmsLog.objects.count(), 0)
        self.assertEqual(Customer.objects.count(), 0)
        self.assertEqual(Order.objects.count(), 0)

    def test_sms_verification_request_creates_no_customer_or_order_and_hides_code(self):
        response = self.request_code()

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["masked_phone"], "***5678")
        self.assertEqual(Customer.objects.count(), 0)
        self.assertEqual(Order.objects.count(), 0)
        challenge = PublicBookingVerification.objects.get()
        self.assertNotIn("123456", challenge.code_hash)
        self.assertTrue(check_password("123456", challenge.code_hash))
        otp_log = SmsLog.objects.get(pk=challenge.sms_log_id)
        self.assertEqual(otp_log.status, SmsLog.Status.DUMMY)
        self.assertEqual(otp_log.store, self.store)
        self.assertNotIn("123456", otp_log.body)
        self.assertNotIn("09012345678", otp_log.body)

    def test_correct_code_atomically_confirms_booking_and_issues_customer_invitation(self):
        requested = self.request_code()
        confirmed = self.client.post(
            "/api/public/booking/confirm/",
            {
                "verification_id": requested.data["verification_id"],
                "code": "123456",
            },
            format="json",
        )

        self.assertEqual(confirmed.status_code, 201, confirmed.data)
        self.assertEqual(confirmed.data["status"], Order.Status.CONFIRMED)
        self.assertEqual(confirmed.data["room_address"], self.room.address)
        customer = Customer.objects.get()
        self.assertEqual(customer.phone, "09012345678")
        self.assertEqual(customer.display_name, "公開予約 太郎")
        order = Order.objects.get()
        self.assertEqual(order.customer, customer)
        self.assertEqual(order.room, self.room)
        self.assertEqual(order.status, Order.Status.CONFIRMED)
        self.assertEqual(order.total_price, 22000)
        self.assertEqual(list(order.options.all()), [self.option])
        challenge = PublicBookingVerification.objects.get()
        self.assertIsNotNone(challenge.consumed_at)
        self.assertTrue(CustomerAccountInvitation.objects.filter(order=order).exists())

    def test_wrong_code_changes_nothing_and_counts_attempt(self):
        requested = self.request_code()
        response = self.client.post(
            "/api/public/booking/confirm/",
            {
                "verification_id": requested.data["verification_id"],
                "code": "999999",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(Customer.objects.count(), 0)
        self.assertEqual(Order.objects.count(), 0)
        challenge = PublicBookingVerification.objects.get()
        self.assertEqual(challenge.failed_attempts, 1)
        self.assertIsNone(challenge.consumed_at)

    def test_verification_is_single_use(self):
        requested = self.request_code()
        body = {
            "verification_id": requested.data["verification_id"],
            "code": "123456",
        }

        first = self.client.post("/api/public/booking/confirm/", body, format="json")
        replay = self.client.post("/api/public/booking/confirm/", body, format="json")

        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(replay.status_code, 400, replay.data)
        self.assertEqual(Order.objects.count(), 1)

    def test_slot_is_rechecked_after_sms_and_conflict_creates_nothing(self):
        requested = self.request_code()
        other_customer = Customer.objects.create(
            store=self.store,
            phone="08011112222",
            display_name="先約",
        )
        Order.objects.create(
            store=self.store,
            cast=self.cast,
            room=self.room,
            customer=other_customer,
            course=self.course,
            course_name=self.course.name,
            course_price=self.course.price,
            total_price=self.course.price,
            start=datetime(2030, 1, 15, 12, 30, tzinfo=TOKYO),
            end=datetime(2030, 1, 15, 14, 30, tzinfo=TOKYO),
            status=Order.Status.CONFIRMED,
        )

        response = self.client.post(
            "/api/public/booking/confirm/",
            {
                "verification_id": requested.data["verification_id"],
                "code": "123456",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(Order.objects.count(), 1)
        challenge = PublicBookingVerification.objects.get()
        self.assertIsNone(challenge.consumed_at)

    def test_verified_existing_phone_reuses_customer_without_overwriting_name(self):
        existing = Customer.objects.create(
            store=self.store,
            phone="090-1234-5678",
            display_name="既存顧客名",
        )
        requested = self.request_code(display_name="入力された別名")
        response = self.client.post(
            "/api/public/booking/confirm/",
            {
                "verification_id": requested.data["verification_id"],
                "code": "123456",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Customer.objects.count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.display_name, "既存顧客名")
        self.assertEqual(Order.objects.get().customer, existing)

    def test_cross_store_option_is_rejected_before_sms(self):
        response = self.request_code(options=[self.other_option.id])

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(PublicBookingVerification.objects.count(), 0)
        self.assertEqual(SmsLog.objects.count(), 0)
        self.assertEqual(Customer.objects.count(), 0)
        self.assertEqual(Order.objects.count(), 0)

    @override_settings(SMS_DUMMY_MODE=False)
    def test_missing_sms_configuration_fails_closed_without_customer_or_order(self):
        with patch("core.services.notify.TWILIO_ACCOUNT_SID", ""), \
             patch("core.services.notify.TWILIO_AUTH_TOKEN", ""), \
             patch("core.services.notify.TWILIO_FROM_PHONE", ""), \
             patch(
                 "core.services.public_booking.generate_public_booking_code",
                 return_value="123456",
             ):
            response = self.client.post(
                "/api/public/booking/request-verification/",
                self.payload(),
                format="json",
            )

        self.assertEqual(response.status_code, 503, response.data)
        self.assertEqual(PublicBookingVerification.objects.count(), 0)
        self.assertEqual(Customer.objects.count(), 0)
        self.assertEqual(Order.objects.count(), 0)
        log = SmsLog.objects.get()
        self.assertEqual(log.status, SmsLog.Status.CONFIG_MISSING)
        self.assertNotEqual(log.status, SmsLog.Status.SENT)

    @override_settings(SMS_DUMMY_MODE=False)
    def test_configured_twilio_sender_requests_real_delivery_without_creating_booking(self):
        with patch("core.services.notify.TWILIO_ACCOUNT_SID", "AC_TEST"), \
             patch("core.services.notify.TWILIO_AUTH_TOKEN", "AUTH_TEST"), \
             patch("core.services.notify.TWILIO_FROM_PHONE", "+815000000000"), \
             patch("twilio.rest.Client") as client_class, \
             patch(
                 "core.services.public_booking.generate_public_booking_code",
                 return_value="123456",
             ):
            client_class.return_value.messages.create.return_value.sid = "SM_TEST"
            response = self.client.post(
                "/api/public/booking/request-verification/",
                self.payload(),
                format="json",
            )

        self.assertEqual(response.status_code, 201, response.data)
        client_class.assert_called_once_with("AC_TEST", "AUTH_TEST")
        client_class.return_value.messages.create.assert_called_once_with(
            body=(
                "【Roomink】Web予約の認証コードは 123456 です。\n"
                "10分以内に予約画面へ入力してください。"
            ),
            from_="+815000000000",
            to="+819012345678",
        )
        log = SmsLog.objects.get()
        self.assertEqual(log.status, SmsLog.Status.SENT)
        self.assertEqual(log.provider, SmsLog.Provider.TWILIO)
        self.assertEqual(log.provider_message_id, "SM_TEST")
        self.assertEqual(Customer.objects.count(), 0)
        self.assertEqual(Order.objects.count(), 0)
