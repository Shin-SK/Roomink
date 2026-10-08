from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import (
    OperationGroupMembership,
    Store,
    StoreInvitation,
    StoreMembership,
    UserProfile,
)


User = get_user_model()


class OperationGroupSettingsTest(TestCase):
    def setUp(self):
        self.a = Store.objects.create(name="運営A店")
        self.b = Store.objects.create(name="運営B店")
        self.c = Store.objects.create(name="無関係C店")
        self.group = self.a.operation_group
        Store.objects.filter(pk=self.b.pk).update(operation_group=self.group)
        self.b.refresh_from_db()

        self.group_manager = self.user("group-manager", self.a, "manager")
        self.b_manager = self.user("b-manager", self.b, "manager")
        self.c_manager = self.user("c-manager", self.c, "manager")
        self.existing_staff = self.user("existing-staff", self.c, "staff")
        OperationGroupMembership.objects.create(
            operation_group=self.group,
            user=self.group_manager,
        )

    def user(self, username, store, role):
        user = User.objects.create_user(username, password="Operation-group-test-pass-77")
        UserProfile.objects.create(user=user, store=store, role=role)
        return user

    def client_for(self, user, store):
        client = APIClient()
        client.force_authenticate(user)
        client.credentials(HTTP_X_ROOMINK_STORE=str(store.pk))
        return client

    def test_group_manager_only_sees_its_own_group_and_not_store_data(self):
        response = self.client_for(self.group_manager, self.a).get("/api/op/operation-group/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            {store["name"] for store in response.data["stores"]},
            {"運営A店", "運営B店"},
        )
        self.assertNotIn("無関係C店", str(response.data))
        self.assertEqual(
            self.client_for(self.group_manager, self.b).get("/api/customers/").status_code,
            403,
        )

    def test_store_manager_cannot_open_group_settings_without_explicit_group_role(self):
        self.assertEqual(
            self.client_for(self.b_manager, self.b).get("/api/op/operation-group/").status_code,
            403,
        )
        self.assertEqual(
            self.client_for(self.c_manager, self.c).get("/api/op/operation-group/").status_code,
            403,
        )

    def test_group_manager_can_create_staff_only_for_selected_group_stores(self):
        client = self.client_for(self.group_manager, self.a)
        response = client.post(
            "/api/op/operation-group/staff/",
            {
                "username": "new-group-staff",
                "password": "Operation-group-create-77",
                "role": "staff",
                "store_ids": [self.a.pk, self.b.pk],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(username="new-group-staff")
        self.assertEqual(
            set(StoreMembership.objects.filter(user=user, is_active=True).values_list("store_id", flat=True)),
            {self.a.pk, self.b.pk},
        )
        rejected = client.post(
            "/api/op/operation-group/staff/",
            {
                "username": "cross-group-staff",
                "password": "Operation-group-create-88",
                "role": "staff",
                "store_ids": [self.a.pk, self.c.pk],
            },
            format="json",
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertFalse(User.objects.filter(username="cross-group-staff").exists())

    def test_group_manager_invitation_can_be_accepted_for_another_group_store(self):
        invitation_response = self.client_for(self.group_manager, self.a).post(
            "/api/op/operation-group/invitations/",
            {
                "username": self.existing_staff.username,
                "role": "staff",
                "store_ids": [self.b.pk],
            },
            format="json",
        )
        self.assertEqual(invitation_response.status_code, 202, invitation_response.data)
        invitation = StoreInvitation.objects.get(recipient=self.existing_staff, store=self.b)
        accepted = self.client_for(self.existing_staff, self.c).post(
            f"/api/auth/store-invitations/{invitation.pk}/respond/",
            {"action": "accept"},
            format="json",
        )
        self.assertEqual(accepted.status_code, 200, accepted.data)
        self.assertTrue(
            StoreMembership.objects.filter(
                user=self.existing_staff,
                store=self.b,
                is_active=True,
            ).exists()
        )

    def test_group_manager_must_keep_one_active_manager(self):
        client = self.client_for(self.group_manager, self.a)
        self.assertEqual(
            client.post(
                "/api/op/operation-group/managers/",
                {"username": self.group_manager.username, "is_active": False},
                format="json",
            ).status_code,
            400,
        )
        granted = client.post(
            "/api/op/operation-group/managers/",
            {"username": self.b_manager.username, "is_active": True},
            format="json",
        )
        self.assertEqual(granted.status_code, 200, granted.data)
        self.assertTrue(
            OperationGroupMembership.objects.filter(
                operation_group=self.group,
                user=self.b_manager,
                is_active=True,
            ).exists()
        )
