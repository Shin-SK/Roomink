from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import CallLog, CallLogReadReceipt, Cast, CastNote, Customer, Store, UserProfile


User = get_user_model()


class OperatorApiPermissionTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="権限テスト店舗")
        self.manager = self.create_user("permission_manager", UserProfile.Role.MANAGER)
        self.staff = self.create_user("permission_staff", UserProfile.Role.STAFF)
        self.cast_user = self.create_user("permission_cast", UserProfile.Role.CAST)
        self.customer_user = User.objects.create_user("permission_customer")
        Cast.objects.create(store=self.store, user=self.cast_user, name="権限テストキャスト")
        Customer.objects.create(
            store=self.store,
            user=self.customer_user,
            phone="07000000001",
            display_name="権限テスト顧客",
        )

        self.manager_client = self.client_for(self.manager)
        self.staff_client = self.client_for(self.staff)
        self.cast_client = self.client_for(self.cast_user)
        self.customer_client = self.client_for(self.customer_user)

    def create_user(self, username, role):
        user = User.objects.create_user(username)
        UserProfile.objects.create(user=user, store=self.store, role=role)
        return user

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def assert_forbidden(self, client, method, path, data=None):
        response = getattr(client, method)(path, data or {}, format="json")
        self.assertEqual(response.status_code, 403, (method, path, response.data))

    def test_cast_and_customer_cannot_read_operator_collections(self):
        protected_paths = [
            "/api/orders/",
            "/api/shifts/",
            "/api/customers/",
            "/api/casts/",
            "/api/courses/",
            "/api/options/",
            "/api/extensions/",
            "/api/nomination-fees/",
            "/api/discounts/",
            "/api/media/",
            "/api/staffs/",
            "/api/cast-expenses/",
            "/api/cast-expense-templates/",
            "/api/cast-expense-template-histories/",
            "/api/cast-checkouts/",
            "/api/cast-adjustments/",
            "/api/cast-notes/",
            "/api/shift-confirm-notification-logs/",
            "/api/point-logs/",
            "/api/op/shift-requests/",
            "/api/op/call-logs/",
            "/api/op/store-phones/",
        ]

        for client in (self.cast_client, self.customer_client):
            for path in protected_paths:
                with self.subTest(role=client, path=path):
                    self.assert_forbidden(client, "get", path)

    def test_cast_and_customer_cannot_call_operator_api_views(self):
        protected_requests = [
            ("get", "/api/op/schedule/?date=2026-08-12"),
            ("get", "/api/op/room-schedule/?date=2026-08-12"),
            ("get", "/api/op/shifts/weekly/?start=2026-08-10"),
            ("get", "/api/op/sales-summary/?date_from=2026-08-12&date_to=2026-08-12"),
            ("get", "/api/op/customers-export.csv"),
            ("get", "/api/op/csv-import/template/?model=customer"),
            ("get", "/api/op/line-alerts/"),
            ("get", "/api/op/shift-end-alerts/"),
            ("get", "/api/op/sms-templates/"),
            ("get", "/api/op/public-booking-settings/"),
            ("get", "/api/op/sip-provisioning/settings/"),
            ("get", "/api/op/cti/queue/"),
            ("post", "/api/op/orders/1/cast-ack/"),
            ("post", "/api/op/csv-import/"),
            ("post", "/api/op/sms-templates/"),
            ("post", "/api/op/sip-reception-devices/"),
        ]

        for client in (self.cast_client, self.customer_client):
            for method, path in protected_requests:
                with self.subTest(role=client, method=method, path=path):
                    self.assert_forbidden(client, method, path)

    def test_cast_cannot_mutate_operator_resources(self):
        protected_paths = [
            "/api/orders/",
            "/api/customers/",
            "/api/casts/",
            "/api/courses/",
            "/api/options/",
            "/api/rooms/",
            "/api/extensions/",
            "/api/nomination-fees/",
            "/api/discounts/",
            "/api/media/",
            "/api/staffs/",
        ]

        for path in protected_paths:
            with self.subTest(path=path):
                self.assert_forbidden(self.cast_client, "post", path)

    def test_staff_cannot_manage_staff_or_mutate_master_data(self):
        self.assert_forbidden(self.staff_client, "get", "/api/staffs/")
        self.assert_forbidden(
            self.staff_client,
            "post",
            "/api/staffs/",
            {
                "username": "unauthorized_manager",
                "password": "not-used-password",
                "role": UserProfile.Role.MANAGER,
            },
        )

        for path in [
            "/api/casts/",
            "/api/courses/",
            "/api/options/",
            "/api/rooms/",
            "/api/extensions/",
            "/api/nomination-fees/",
            "/api/discounts/",
            "/api/media/",
            "/api/op/store-phones/",
        ]:
            with self.subTest(path=path):
                self.assert_forbidden(self.staff_client, "post", path)

        self.assertFalse(User.objects.filter(username="unauthorized_manager").exists())

    def test_existing_allowed_read_paths_remain_available(self):
        staff_paths = [
            "/api/orders/",
            "/api/shifts/",
            "/api/customers/",
            "/api/casts/",
            "/api/courses/",
            "/api/options/",
            "/api/rooms/",
            "/api/extensions/",
            "/api/nomination-fees/",
            "/api/discounts/",
            "/api/media/",
        ]
        for path in staff_paths:
            with self.subTest(role="staff", path=path):
                self.assertEqual(self.staff_client.get(path).status_code, 200)

        self.assertEqual(self.manager_client.get("/api/staffs/").status_code, 200)
        self.assertEqual(self.cast_client.get("/api/rooms/").status_code, 200)
        self.assertEqual(self.cast_client.get("/api/cast/today/").status_code, 200)

    def test_staff_can_read_notes_but_cannot_change_them(self):
        note = CastNote.objects.create(
            store=self.store,
            title="スタッフ閲覧用ノート",
            status=CastNote.Status.PUBLISHED,
            visibility=CastNote.Visibility.STAFF,
        )

        response = self.staff_client.get("/api/cast-notes/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([item["id"] for item in response.data["results"]], [note.id])

        self.assert_forbidden(
            self.staff_client,
            "post",
            "/api/cast-notes/",
            {"title": "不正作成"},
        )
        self.assert_forbidden(
            self.staff_client,
            "patch",
            f"/api/cast-notes/{note.id}/",
            {"title": "不正変更"},
        )
        note.refresh_from_db()
        self.assertEqual(note.title, "スタッフ閲覧用ノート")

    def test_cti_mutations_are_limited_to_the_operator_store(self):
        own_call = CallLog.objects.create(
            store=self.store,
            contact_id="permission-own-call",
            from_phone="07000000002",
            to_phone="05000000001",
        )
        other_store = Store.objects.create(name="別店舗")
        other_call = CallLog.objects.create(
            store=other_store,
            contact_id="permission-other-call",
            from_phone="07000000003",
            to_phone="05000000002",
        )

        own_response = self.staff_client.post(f"/api/op/cti/calls/{own_call.id}/start/")
        other_response = self.staff_client.post(f"/api/op/cti/calls/{other_call.id}/start/")

        self.assertEqual(own_response.status_code, 200, own_response.data)
        self.assertEqual(other_response.status_code, 404, other_response.data)
        other_call.refresh_from_db()
        self.assertEqual(other_call.status, CallLog.Status.NEW)

    def test_cti_read_receipt_is_personal_and_does_not_change_workflow_status(self):
        call = CallLog.objects.create(
            store=self.store,
            contact_id="permission-read-receipt",
            from_phone="07000000004",
            to_phone="05000000001",
        )

        response = self.staff_client.post(
            "/api/op/cti/calls/mark-seen/",
            {"call_ids": [call.id]},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(CallLogReadReceipt.objects.filter(call=call, user=self.staff).exists())
        call.refresh_from_db()
        self.assertEqual(call.status, CallLog.Status.NEW)

        staff_queue = self.staff_client.get("/api/op/cti/queue/")
        manager_queue = self.manager_client.get("/api/op/cti/queue/")
        self.assertTrue(staff_queue.data["calls"][0]["seen_by_me"])
        self.assertFalse(manager_queue.data["calls"][0]["seen_by_me"])

    def test_platform_dashboard_and_store_switch_are_superuser_only(self):
        admin = User.objects.create_superuser("platform_admin", password="test-password")
        UserProfile.objects.create(user=admin, store=self.store, role=UserProfile.Role.MANAGER)
        admin_client = self.client_for(admin)
        other_store = Store.objects.create(name="切替先店舗")

        forbidden = self.manager_client.get("/api/platform/dashboard/")
        self.assertEqual(forbidden.status_code, 403, forbidden.data)

        dashboard = admin_client.get("/api/platform/dashboard/")
        self.assertEqual(dashboard.status_code, 200, dashboard.data)
        dashboard_store_ids = {row["id"] for row in dashboard.data["stores"]}
        self.assertTrue({self.store.id, other_store.id}.issubset(dashboard_store_ids))

        switched = admin_client.post(
            "/api/platform/active-store/",
            {"store_id": other_store.id},
            format="json",
        )
        self.assertEqual(switched.status_code, 200, switched.data)
        me = admin_client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200, me.data)
        self.assertEqual(me.data["role"], "superuser")
        self.assertTrue(me.data["is_superuser"])
        self.assertEqual(me.data["store_id"], other_store.id)

    def test_phone_settings_are_platform_admin_only(self):
        response = self.manager_client.get("/api/op/store-phones/")
        self.assertEqual(response.status_code, 403, response.data)

        admin = User.objects.create_superuser("phone_admin", password="test-password")
        UserProfile.objects.create(user=admin, store=self.store, role=UserProfile.Role.MANAGER)
        admin_client = self.client_for(admin)
        response = admin_client.get("/api/op/store-phones/")
        self.assertEqual(response.status_code, 200, response.data)
