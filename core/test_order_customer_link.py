from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    Cast,
    Course,
    Customer,
    Order,
    OrderServiceRecipientLinkLog,
    Room,
    Store,
    UserProfile,
)
from core.services.business_datetime import build_store_datetime, business_date_for_datetime


User = get_user_model()


class OrderCustomerLinkTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="予約紐付け店舗", timezone="Asia/Tokyo")
        self.other_store = Store.objects.create(name="別店舗", timezone="Asia/Tokyo")
        self.manager = self.create_operator("link_manager", UserProfile.Role.MANAGER)
        self.staff = self.create_operator("link_staff", UserProfile.Role.STAFF)
        self.cast = Cast.objects.create(store=self.store, name="紐付けキャスト")
        self.room = Room.objects.create(store=self.store, name="101")
        self.course = Course.objects.create(
            store=self.store,
            name="60分",
            duration=60,
            price=10000,
        )
        self.contact_user = User.objects.create_user("link_contact", password="pass")
        self.contact = Customer.objects.create(
            store=self.store,
            user=self.contact_user,
            phone="09011112222",
            display_name="代表者A",
        )
        self.recipient_user = User.objects.create_user("link_recipient", password="pass")
        self.recipient = Customer.objects.create(
            store=self.store,
            user=self.recipient_user,
            phone="09033334444",
            display_name="利用者B",
        )
        self.other_customer = Customer.objects.create(
            store=self.other_store,
            phone="09099990000",
            display_name="別店舗顧客",
        )
        business_date = business_date_for_datetime(
            timezone.now(), self.store.timezone,
        ) - timedelta(days=2)
        start = build_store_datetime(
            business_date,
            time(18, 0),
            timezone_name=self.store.timezone,
        )
        self.order = Order.objects.create(
            store=self.store,
            cast=self.cast,
            room=self.room,
            customer=self.contact,
            service_recipient_name="利用者B",
            course=self.course,
            course_name=self.course.name,
            course_price=self.course.price,
            total_price=self.course.price,
            start=start,
            end=start + timedelta(hours=1),
            status=Order.Status.DONE,
        )
        self.manager_client = self.client_as(self.manager)
        self.staff_client = self.client_as(self.staff)
        self.recipient_client = self.client_as(self.recipient_user)

    def create_operator(self, username, role):
        user = User.objects.create_user(username, password="pass")
        UserProfile.objects.create(user=user, store=self.store, role=role)
        return user

    def client_as(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def link(self, client, customer_id):
        return client.post(
            f"/api/orders/{self.order.id}/link-service-recipient/",
            {"customer_id": customer_id},
            format="json",
        )

    def test_manager_links_past_order_without_changing_contact(self):
        response = self.link(self.manager_client, self.recipient.id)

        self.assertEqual(response.status_code, 200, response.data)
        self.order.refresh_from_db()
        self.assertEqual(self.order.customer, self.contact)
        self.assertEqual(self.order.service_recipient_customer, self.recipient)
        self.assertEqual(self.order.service_recipient_name, "利用者B")
        log = OrderServiceRecipientLinkLog.objects.get(order=self.order)
        self.assertIsNone(log.previous_customer_id)
        self.assertEqual(log.linked_customer_id, self.recipient.id)
        self.assertEqual(log.linked_customer_name, "利用者B")
        self.assertEqual(log.executed_by, self.manager)

    def test_staff_cannot_link_order(self):
        response = self.link(self.staff_client, self.recipient.id)

        self.assertEqual(response.status_code, 403, response.data)
        self.order.refresh_from_db()
        self.assertIsNone(self.order.service_recipient_customer)
        self.assertFalse(OrderServiceRecipientLinkLog.objects.exists())

    def test_other_store_customer_is_rejected(self):
        response = self.link(self.manager_client, self.other_customer.id)

        self.assertEqual(response.status_code, 400, response.data)
        self.order.refresh_from_db()
        self.assertIsNone(self.order.service_recipient_customer)
        self.assertFalse(OrderServiceRecipientLinkLog.objects.exists())

    def test_linked_customer_can_view_history_and_reservation(self):
        before = self.recipient_client.get(f"/api/cu/reservations/{self.order.id}/")
        self.assertEqual(before.status_code, 404, before.data)

        linked = self.link(self.manager_client, self.recipient.id)
        self.assertEqual(linked.status_code, 200, linked.data)

        mypage = self.recipient_client.get("/api/cu/mypage/")
        detail = self.recipient_client.get(f"/api/cu/reservations/{self.order.id}/")
        self.assertEqual(mypage.status_code, 200, mypage.data)
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertIn(self.order.id, [item["id"] for item in mypage.data["history"]])

    def test_unlink_removes_recipient_access_and_keeps_name_snapshot(self):
        self.link(self.manager_client, self.recipient.id)
        response = self.link(self.manager_client, None)

        self.assertEqual(response.status_code, 200, response.data)
        self.order.refresh_from_db()
        self.assertIsNone(self.order.service_recipient_customer)
        self.assertEqual(self.order.service_recipient_name, "利用者B")
        self.assertEqual(OrderServiceRecipientLinkLog.objects.count(), 2)
        latest = OrderServiceRecipientLinkLog.objects.first()
        self.assertEqual(latest.previous_customer_id, self.recipient.id)
        self.assertIsNone(latest.linked_customer_id)
        detail = self.recipient_client.get(f"/api/cu/reservations/{self.order.id}/")
        self.assertEqual(detail.status_code, 404, detail.data)

    def test_customer_merge_moves_recipient_link(self):
        duplicate = Customer.objects.create(
            store=self.store,
            phone="09055556666",
            display_name="利用者B旧",
        )
        self.link(self.manager_client, duplicate.id)

        response = self.manager_client.post(
            f"/api/customers/{self.recipient.id}/merge/",
            {"merge_id": duplicate.id},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.order.refresh_from_db()
        self.assertEqual(self.order.service_recipient_customer, self.recipient)
