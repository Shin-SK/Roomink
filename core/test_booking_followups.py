from datetime import timedelta

from django.test import TestCase, override_settings

from core import test_order_extension_duration as extension_fixtures
from core import test_public_web_booking as public_fixtures
from core.models import Course, DailySettlement, Discount, Extension, NominationFee, Order, SmsLog, Store


@override_settings(SMS_DUMMY_MODE=True, DJANGO_EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class BookingEditFollowupsTest(TestCase):
    def setUp(self):
        self.f = extension_fixtures.OrderExtensionDurationTest()
        self.f.setUp()

    def test_single_save_updates_discount_extension_nomination_and_reloads(self):
        f = self.f
        order = f.create_order()
        discount = Discount.objects.create(store=f.store, name="2000円割引", value=2000)
        nomination = NominationFee.objects.create(store=f.store, name="写真指名", price=1000)
        response = f.client.patch(f"/api/orders/{order.pk}/", {
            "discount": discount.pk, "extension": f.extension.pk,
            "extension_duration": 30, "extension_price": 5000,
            "nomination_fee": nomination.pk,
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        order.refresh_from_db()
        self.assertEqual(order.total_price, 14000)
        self.assertEqual(order.end, order.start + timedelta(minutes=90))
        reloaded = f.client.get(f"/api/orders/{order.pk}/")
        self.assertEqual(reloaded.data["discount"], discount.pk)
        self.assertEqual(reloaded.data["discount_amount"], 2000)
        self.assertEqual(SmsLog.objects.count(), 0)
        removed = f.client.patch(f"/api/orders/{order.pk}/", {"discount": None}, format="json")
        self.assertEqual(removed.status_code, 200, removed.data)
        self.assertEqual(removed.data["total_price"], 16000)

    def test_course_change_ignores_stale_end_and_preserves_extension(self):
        f = self.f
        order = f.create_order()
        order.extension_duration = 30
        order.extension_price = 5000
        order.save()
        course = Course.objects.create(store=f.store, name="90分", duration=90, price=15000)
        response = f.client.patch(f"/api/orders/{order.pk}/", {
            "course": course.pk, "end": order.end.isoformat(),
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        order.refresh_from_db()
        self.assertEqual(order.end, order.start + timedelta(minutes=120))
        self.assertEqual(order.total_price, 20000)

    def test_pending_finalize_can_correct_but_done_and_cancelled_cannot(self):
        f = self.f
        order = f.create_order()
        discount = Discount.objects.create(store=f.store, name="割引", value=1000)
        order.status = Order.Status.PENDING_FINALIZE
        order.save()
        url = f"/api/orders/{order.pk}/"
        response = f.client.patch(url, {"discount": discount.pk, "extension_duration": 15, "extension_price": 2000}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["total_price"], 11000)
        for status in (Order.Status.DONE, Order.Status.CANCELLED):
            order.refresh_from_db()
            order.status = status
            order.save()
            self.assertEqual(f.client.patch(url, {"discount": None}, format="json").status_code, 400)

    def test_invalid_discount_rolls_back_whole_save_and_cast_cannot_edit(self):
        f = self.f
        order = f.create_order()
        discount = Discount.objects.create(store=f.store, name="無効", value=1000, is_active=False)
        url = f"/api/orders/{order.pk}/"
        response = f.client.patch(url, {"discount": discount.pk, "memo": "must not persist"}, format="json")
        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.memo, "")
        self.assertEqual(f.cast_client.patch(url, {"discount": None}, format="json").status_code, 403)

    def test_foreign_addons_and_locked_day_are_rejected(self):
        f = self.f
        order = f.create_order()
        other = Store.objects.create(name="別店舗")
        foreign_discount = Discount.objects.create(store=other, name="別店舗割引", value=1000)
        foreign_extension = Extension.objects.create(store=other, name="別店舗延長", duration=30, price=5000)
        url = f"/api/orders/{order.pk}/"
        for payload in ({"discount": foreign_discount.pk}, {"extension": foreign_extension.pk}, {"extension_duration": 7}):
            self.assertEqual(f.client.patch(url, payload, format="json").status_code, 400)
        DailySettlement.objects.create(store=f.store, date=f.business_date, status="LOCKED")
        self.assertEqual(f.client.patch(url, {"discount": None}, format="json").status_code, 400)

    def test_longer_course_conflict_does_not_partially_save_discount(self):
        f = self.f
        order = f.create_order()
        f.create_order(start_hour=14, end_hour=15)
        course = Course.objects.create(store=f.store, name="180分", duration=180, price=30000)
        discount = Discount.objects.create(store=f.store, name="割引", value=1000)
        response = f.client.patch(f"/api/orders/{order.pk}/", {"course": course.pk, "discount": discount.pk}, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        order.refresh_from_db()
        self.assertEqual(order.course_id, f.course.pk)
        self.assertIsNone(order.discount_id)

    def test_extension_beyond_shift_and_overnight_course_recalculation(self):
        f = self.f
        order = f.create_order(start_hour=17, end_hour=18)
        response = f.client.patch(f"/api/orders/{order.pk}/", {"extension_duration": 30, "extension_price": 5000}, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("シフト", str(response.data))
        order.room = None
        order.start = order.start.replace(hour=23, minute=30)
        order.end = order.start + timedelta(minutes=60)
        order.save()
        course = Course.objects.create(store=f.store, name="90分", duration=90, price=15000)
        response = f.client.patch(f"/api/orders/{order.pk}/", {"course": course.pk}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["end_time_extended"], "25:00")

    def test_percentage_discount_recalculates_and_never_goes_below_zero(self):
        f = self.f
        order = f.create_order()
        discount = Discount.objects.create(store=f.store, name="10%", discount_type="percent", value=10)
        url = f"/api/orders/{order.pk}/"
        response = f.client.patch(url, {"discount": discount.pk, "extension_duration": 15, "extension_price": 1235}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["total_price"], 10112)
        discount = Discount.objects.create(store=f.store, name="全額以上", value=99999)
        response = f.client.patch(url, {"discount": discount.pk}, format="json")
        self.assertEqual(response.data["total_price"], 0)


@override_settings(SMS_DUMMY_MODE=True, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", FRONTEND_URL="https://roomink.example", RESERVATION_LINK_BASE_URL="https://r.roomink.example")
class PublicBookingFollowupsTest(TestCase):
    def setUp(self):
        self.f = public_fixtures.PublicWebBookingTest()
        self.f.setUp()

    def test_nomination_and_payment_persist_through_sms_verification(self):
        f = self.f
        fee = NominationFee.objects.create(store=f.store, name="本指名", price=2000)
        requested = f.request_code(nomination_fee=fee.pk, payment_method="CASH")
        self.assertEqual(requested.status_code, 201, requested.data)
        response = f.client.post("/api/public/booking/confirm/", {
            "verification_id": requested.data["verification_id"], "code": "123456",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get()
        self.assertEqual(order.total_price, 24000)
        self.assertEqual(order.nomination_fee_name, "本指名")
        self.assertEqual(order.payment_method, "CASH")

    def test_card_is_pending_payment_and_does_not_expose_room(self):
        f = self.f
        requested = f.request_code(payment_method="CARD")
        self.assertEqual(requested.status_code, 201, requested.data)
        response = f.client.post("/api/public/booking/confirm/", {
            "verification_id": requested.data["verification_id"], "code": "123456",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["payment_method"], "CARD")
        self.assertEqual(response.data["room_address"], "")
        self.assertEqual(response.data["room_name"], "")
        self.assertTrue(SmsLog.objects.filter(template_type="CARD_PAYMENT_REQUEST").exists())

    def test_invalid_payment_and_foreign_or_inactive_nomination_are_rejected(self):
        f = self.f
        for value in ("PAYPAY", "UNSET", "", None):
            self.assertEqual(f.request_code(payment_method=value).status_code, 400)
        foreign = NominationFee.objects.create(store=f.other_store, name="写真指名", price=1000)
        inactive = NominationFee.objects.create(store=f.store, name="本指名", price=2000, is_active=False)
        for fee in (foreign, inactive):
            self.assertEqual(f.request_code(nomination_fee=fee.pk).status_code, 400)
        self.assertFalse(Order.objects.exists())
