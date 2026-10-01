from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import (
    OperatorNotification,
    OperatorNotificationReadReceipt,
    Store,
    UserProfile,
)


User = get_user_model()


class OperatorNotificationApiTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="通知店舗")
        self.other_store = Store.objects.create(name="他店舗")
        self.manager = User.objects.create_user("notification_manager", password="pass")
        self.staff = User.objects.create_user("notification_staff", password="pass")
        self.cast_user = User.objects.create_user("notification_cast", password="pass")
        UserProfile.objects.create(
            user=self.manager,
            store=self.store,
            role=UserProfile.Role.MANAGER,
        )
        UserProfile.objects.create(
            user=self.staff,
            store=self.store,
            role=UserProfile.Role.STAFF,
        )
        UserProfile.objects.create(
            user=self.cast_user,
            store=self.store,
            role=UserProfile.Role.CAST,
        )
        self.notification = OperatorNotification.objects.create(
            store=self.store,
            kind=OperatorNotification.Kind.PUBLIC_BOOKING,
            title="Web予約が入りました",
            message="10月1日 14:00〜15:00",
            target_path="/op/schedule?date=2030-10-01",
        )
        OperatorNotification.objects.create(
            store=self.other_store,
            kind=OperatorNotification.Kind.PUBLIC_BOOKING,
            title="別店舗の予約",
        )

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_manager_only_sees_own_store_and_can_mark_read(self):
        client = self.client_for(self.manager)

        listed = client.get("/api/op/notifications/")
        marked = client.post(
            "/api/op/notifications/",
            {"notification_ids": [self.notification.id]},
            format="json",
        )
        listed_again = client.get("/api/op/notifications/")

        self.assertEqual(listed.status_code, 200, listed.data)
        self.assertEqual(listed.data["unread_count"], 1)
        self.assertEqual(
            [item["id"] for item in listed.data["notifications"]],
            [self.notification.id],
        )
        self.assertEqual(marked.status_code, 200, marked.data)
        self.assertEqual(marked.data["unread_count"], 0)
        self.assertTrue(
            OperatorNotificationReadReceipt.objects.filter(
                notification=self.notification,
                user=self.manager,
            ).exists()
        )
        self.assertTrue(listed_again.data["notifications"][0]["is_read"])

    def test_read_status_is_independent_for_each_operator(self):
        OperatorNotificationReadReceipt.objects.create(
            notification=self.notification,
            user=self.manager,
        )

        staff_response = self.client_for(self.staff).get("/api/op/notifications/")

        self.assertEqual(staff_response.status_code, 200, staff_response.data)
        self.assertEqual(staff_response.data["unread_count"], 1)
        self.assertFalse(staff_response.data["notifications"][0]["is_read"])

    def test_cast_cannot_read_operator_notifications(self):
        response = self.client_for(self.cast_user).get("/api/op/notifications/")

        self.assertEqual(response.status_code, 403, response.data)
