from datetime import time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    Cast,
    Course,
    Customer,
    CustomerAccountInvitation,
    Order,
    Room,
    ShiftAssignment,
    SmsLog,
    Store,
    UserProfile,
)
from core.services.business_datetime import (
    build_store_datetime,
    business_date_for_datetime,
)
from core.services.notify import notify_order_confirmed
from core.services.sales import get_sales_summary


User = get_user_model()


@override_settings(FRONTEND_URL="https://roomink.example", SMS_DUMMY_MODE=True)
class OrderServiceRecipientTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="実利用者テスト店舗", timezone="Asia/Tokyo")
        self.manager = self.create_operator("recipient_manager", UserProfile.Role.MANAGER)
        self.staff = self.create_operator("recipient_staff", UserProfile.Role.STAFF)
        self.cast_user = self.create_operator("recipient_cast", UserProfile.Role.CAST)
        self.cast = Cast.objects.create(
            store=self.store,
            user=self.cast_user,
            name="実利用者テストキャスト",
        )
        self.room = Room.objects.create(store=self.store, name="101")
        self.course = Course.objects.create(
            store=self.store,
            name="60分",
            duration=60,
            price=10000,
        )
        self.contact_user = User.objects.create_user("recipient_contact", password="customer-pass")
        self.contact = Customer.objects.create(
            store=self.store,
            user=self.contact_user,
            phone="09011112222",
            display_name="代表者A",
        )
        self.other_user = User.objects.create_user("recipient_other", password="other-pass")
        self.other_customer = Customer.objects.create(
            store=self.store,
            user=self.other_user,
            phone="09033334444",
            display_name="利用者B",
        )
        self.business_date = business_date_for_datetime(
            timezone.now(), self.store.timezone,
        ) + timedelta(days=2)
        ShiftAssignment.objects.create(
            store=self.store,
            date=self.business_date,
            cast=self.cast,
            room=self.room,
            start_time=time(10, 0),
            end_time=time(23, 0),
        )
        self.manager_client = self.client_as(self.manager)
        self.staff_client = self.client_as(self.staff)
        self.cast_client = self.client_as(self.cast_user)
        self.contact_client = self.client_as(self.contact_user)
        self.other_customer_client = self.client_as(self.other_user)

    def create_operator(self, username, role):
        user = User.objects.create_user(username, password="operator-pass")
        UserProfile.objects.create(user=user, store=self.store, role=role)
        return user

    def client_as(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def start_at(self, hour):
        return build_store_datetime(
            self.business_date,
            time(hour, 0),
            timezone_name=self.store.timezone,
        )

    def order_payload(self, hour=12, **overrides):
        payload = {
            "cast": self.cast.id,
            "customer": self.contact.id,
            "course": self.course.id,
            "start": self.start_at(hour).isoformat(),
        }
        payload.update(overrides)
        return payload

    def create_order(self, hour=12, status=Order.Status.REQUESTED, **overrides):
        start = self.start_at(hour)
        values = {
            "store": self.store,
            "cast": self.cast,
            "room": self.room,
            "customer": self.contact,
            "course": self.course,
            "course_name": self.course.name,
            "course_price": self.course.price,
            "total_price": self.course.price,
            "start": start,
            "end": start + timedelta(hours=1),
            "status": status,
        }
        values.update(overrides)
        return Order.objects.create(**values)

    def test_manager_and_staff_create_blank_or_named_recipient_without_customer_creation(self):
        original_customers = Customer.objects.count()

        blank = self.manager_client.post(
            "/api/orders/", self.order_payload(hour=12), format="json",
        )
        named = self.staff_client.post(
            "/api/orders/",
            self.order_payload(hour=14, service_recipient_name="  山田 花子  "),
            format="json",
        )

        self.assertEqual(blank.status_code, 201, blank.data)
        self.assertEqual(named.status_code, 201, named.data)
        self.assertEqual(blank.data["service_recipient_name"], "")
        self.assertEqual(named.data["service_recipient_name"], "山田 花子")
        self.assertEqual(Customer.objects.count(), original_customers)
        self.assertEqual(Order.objects.get(pk=named.data["id"]).customer, self.contact)
        self.assertEqual(Customer.objects.filter(display_name="山田 花子").count(), 0)

    def test_recipient_length_is_validated(self):
        response = self.manager_client.post(
            "/api/orders/",
            self.order_payload(service_recipient_name="あ" * 51),
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("service_recipient_name", response.data)

    def test_manager_and_staff_can_edit_current_recipient(self):
        manager_order = self.create_order(hour=12)
        staff_order = self.create_order(hour=14)

        manager_response = self.manager_client.patch(
            f"/api/orders/{manager_order.id}/",
            {"service_recipient_name": "利用者B"},
            format="json",
        )
        staff_response = self.staff_client.patch(
            f"/api/orders/{staff_order.id}/",
            {"service_recipient_name": "  利用者C  "},
            format="json",
        )

        self.assertEqual(manager_response.status_code, 200, manager_response.data)
        self.assertEqual(staff_response.status_code, 200, staff_response.data)
        manager_order.refresh_from_db()
        staff_order.refresh_from_db()
        self.assertEqual(manager_order.service_recipient_name, "利用者B")
        self.assertEqual(staff_order.service_recipient_name, "利用者C")

    def test_past_order_recipient_obeys_existing_manager_lock(self):
        past_date = business_date_for_datetime(
            timezone.now(), self.store.timezone,
        ) - timedelta(days=1)
        past_start = build_store_datetime(
            past_date, time(18, 0), timezone_name=self.store.timezone,
        )
        order = Order.objects.create(
            store=self.store,
            cast=self.cast,
            room=self.room,
            customer=self.contact,
            course=self.course,
            course_name=self.course.name,
            course_price=self.course.price,
            total_price=self.course.price,
            start=past_start,
            end=past_start + timedelta(hours=1),
        )

        rejected = self.staff_client.patch(
            f"/api/orders/{order.id}/",
            {"service_recipient_name": "スタッフ変更"},
            format="json",
        )
        accepted = self.manager_client.patch(
            f"/api/orders/{order.id}/",
            {"service_recipient_name": "管理者変更"},
            format="json",
        )

        self.assertEqual(rejected.status_code, 403, rejected.data)
        self.assertEqual(accepted.status_code, 200, accepted.data)
        order.refresh_from_db()
        self.assertEqual(order.service_recipient_name, "管理者変更")

    def test_cast_and_customer_cannot_change_recipient(self):
        order = self.create_order()

        cast_response = self.cast_client.patch(
            f"/api/orders/{order.id}/",
            {"service_recipient_name": "不正なキャスト変更"},
            format="json",
        )
        customer_response = self.contact_client.patch(
            f"/api/orders/{order.id}/",
            {"service_recipient_name": "不正な顧客変更"},
            format="json",
        )

        self.assertEqual(cast_response.status_code, 403, cast_response.data)
        self.assertEqual(customer_response.status_code, 403, customer_response.data)
        order.refresh_from_db()
        self.assertEqual(order.service_recipient_name, "")

    def test_customer_booking_cannot_inject_another_recipient(self):
        response = self.contact_client.post(
            "/api/cu/bookings/",
            self.order_payload(hour=16, service_recipient_name="勝手な別人"),
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(pk=response.data["id"])
        self.assertEqual(order.customer, self.contact)
        self.assertEqual(order.service_recipient_name, "")

    def test_multiple_orders_keep_one_contact_and_independent_recipient_snapshots(self):
        original_customers = Customer.objects.count()
        orders = [
            self.create_order(hour=12, service_recipient_name=""),
            self.create_order(hour=14, service_recipient_name="利用者B"),
            self.create_order(hour=16, service_recipient_name="利用者C"),
        ]

        self.assertEqual([order.customer for order in orders], [self.contact] * 3)
        self.assertEqual(
            [order.service_recipient_name for order in orders],
            ["", "利用者B", "利用者C"],
        )
        self.assertEqual(Customer.objects.count(), original_customers)
        self.assertEqual(self.other_customer.orders.count(), 0)

    def test_customer_detail_keeps_contact_ownership_and_shows_recipient(self):
        order = self.create_order(service_recipient_name="利用者B")

        owner = self.contact_client.get(f"/api/cu/reservations/{order.id}/")
        other = self.other_customer_client.get(f"/api/cu/reservations/{order.id}/")

        self.assertEqual(owner.status_code, 200, owner.data)
        self.assertEqual(owner.data["service_recipient_name"], "利用者B")
        self.assertEqual(other.status_code, 404, other.data)

    def test_sms_and_invitation_remain_linked_to_contact(self):
        order = self.create_order(service_recipient_name="利用者B")
        self.contact.user = None
        self.contact.save(update_fields=["user"])

        with patch("core.services.notify.TWILIO_ACCOUNT_SID", ""), \
             patch("core.services.notify.TWILIO_AUTH_TOKEN", ""), \
             patch("core.services.notify.TWILIO_FROM_PHONE", ""):
            log = notify_order_confirmed(order, created_by=self.manager)

        self.assertEqual(log.to_phone, self.contact.phone)
        self.assertEqual(log.customer, self.contact)
        invitation = CustomerAccountInvitation.objects.get(order=order)
        self.assertEqual(invitation.customer, self.contact)
        self.assertEqual(CustomerAccountInvitation.objects.count(), 1)
        self.assertEqual(SmsLog.objects.filter(order=order).count(), 1)
        self.assertEqual(self.other_customer.account_invitations.count(), 0)

    def test_order_search_finds_recipient_without_polluting_customer_search(self):
        order = self.create_order(service_recipient_name="検索専用 花子")
        original_customers = Customer.objects.count()

        order_result = self.manager_client.get("/api/orders/?search=検索専用")
        customer_result = self.manager_client.get("/api/customers/?search=検索専用")

        self.assertEqual(order_result.status_code, 200, order_result.data)
        order_items = order_result.data.get("results", order_result.data)
        customer_items = customer_result.data.get("results", customer_result.data)
        self.assertEqual([item["id"] for item in order_items], [order.id])
        self.assertEqual(customer_items, [])
        self.assertEqual(Customer.objects.count(), original_customers)

    def test_recipient_snapshot_does_not_change_sales_or_contact_visit_count(self):
        order = self.create_order(
            status=Order.Status.DONE,
            service_recipient_name="利用者B",
        )
        summary = get_sales_summary(self.store, self.business_date, self.business_date)
        mypage = self.contact_client.get("/api/cu/mypage/")

        self.assertEqual(summary["total_orders"], 1)
        self.assertEqual(summary["total_sales"], order.total_price)
        self.assertEqual(mypage.status_code, 200, mypage.data)
        self.assertEqual(mypage.data["customer"]["total_visits"], 1)
        self.assertEqual(self.other_customer.orders.count(), 0)

    def test_script_like_name_is_returned_as_data_and_unknown_fk_is_ignored(self):
        original_customers = Customer.objects.count()
        value = '<script>alert("x")</script>'
        response = self.manager_client.post(
            "/api/orders/",
            self.order_payload(
                service_recipient_name=value,
                service_recipient_customer=self.other_customer.id,
            ),
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["service_recipient_name"], value)
        order = Order.objects.get(pk=response.data["id"])
        self.assertEqual(order.customer, self.contact)
        self.assertEqual(Customer.objects.count(), original_customers)
