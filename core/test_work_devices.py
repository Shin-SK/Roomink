import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    CallLog,
    Customer,
    OperationGroup,
    OperationGroupMembership,
    Store,
    StoreMembership,
    UserProfile,
    WorkDevice,
)


class WorkDeviceFoundationTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.group = OperationGroup.objects.create(internal_label="Work test group")
        self.other_group = OperationGroup.objects.create(internal_label="Other group")
        self.store_a = Store.objects.create(name="Work A", operation_group=self.group)
        self.store_b = Store.objects.create(name="Work B", operation_group=self.group)
        self.store_c = Store.objects.create(name="Work C", operation_group=self.other_group)

        user_model = get_user_model()
        self.manager = user_model.objects.create_user("work-manager", password="Strong-pass-123")
        self.staff = user_model.objects.create_user("work-staff", password="Strong-pass-456")
        self.outsider = user_model.objects.create_user("work-outsider", password="Strong-pass-789")
        for user, store, role in (
            (self.manager, self.store_a, UserProfile.Role.MANAGER),
            (self.staff, self.store_b, UserProfile.Role.STAFF),
            (self.outsider, self.store_c, UserProfile.Role.MANAGER),
        ):
            UserProfile.objects.create(user=user, store=store, role=role)
            StoreMembership.objects.update_or_create(
                user=user,
                store=store,
                defaults={"role": role, "is_active": True},
            )
        StoreMembership.objects.create(
            user=self.manager, store=self.store_b, role="manager", is_active=True
        )
        OperationGroupMembership.objects.create(
            operation_group=self.group, user=self.manager
        )
        OperationGroupMembership.objects.create(
            operation_group=self.other_group, user=self.outsider
        )

    def personal_login(self, *, store_ids=None, device_key=None):
        response = self.client.post(
            "/api/work/personal-login/",
            {
                "username": self.manager.username,
                "password": "Strong-pass-123",
                "device_key": str(device_key or uuid.uuid4()),
                "label": "Manager iPhone",
                "platform": "ios",
                "store_ids": store_ids or [self.store_a.pk, self.store_b.pk],
            },
            format="json",
        )
        return response

    def device_client(self, token):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"RoominkWork {token}")
        return client

    def test_personal_login_issues_hashed_device_token_for_owned_stores(self):
        response = self.personal_login()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["token"])
        self.assertEqual(
            {row["id"] for row in response.data["device"]["stores"]},
            {self.store_a.pk, self.store_b.pk},
        )
        device = WorkDevice.objects.get(device_key=response.data["device"]["device_key"])
        self.assertEqual(device.kind, WorkDevice.Kind.PERSONAL)
        credential = device.credentials.get()
        self.assertNotEqual(credential.token_hash, response.data["token"])

        forbidden = self.personal_login(store_ids=[self.store_c.pk])
        self.assertEqual(forbidden.status_code, 403)

    def test_personal_membership_removal_stops_store_calls_immediately(self):
        login = self.personal_login()
        client = self.device_client(login.data["token"])
        customer = Customer.objects.create(
            store=self.store_a, display_name="Test caller", phone="09000000001"
        )
        CallLog.objects.create(
            store=self.store_a,
            contact_id="CA-work-a",
            from_phone=customer.phone,
            to_phone="05000000001",
            customer=customer,
        )
        CallLog.objects.create(
            store=self.store_c,
            contact_id="CA-work-c",
            from_phone="09000000002",
            to_phone="05000000003",
        )
        calls = client.get("/api/work/calls/")
        self.assertEqual(calls.status_code, 200)
        self.assertEqual([row["contact_id"] for row in calls.data["calls"]], ["CA-work-a"])

        membership = StoreMembership.objects.get(user=self.manager, store=self.store_a)
        membership.is_active = False
        membership.save(update_fields=["is_active", "updated_at"])
        calls = client.get("/api/work/calls/")
        self.assertEqual(calls.status_code, 200)
        self.assertEqual(calls.data["calls"], [])
        me = client.get("/api/work/me/")
        self.assertNotIn(self.store_a.pk, {row["id"] for row in me.data["stores"]})

    def test_per_store_receiving_stop_does_not_remove_data_entitlement(self):
        login = self.personal_login()
        client = self.device_client(login.data["token"])
        response = client.post(
            "/api/work/receiving/",
            {"stores": [{"store_id": self.store_a.pk, "is_receiving": False}]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        store_a = next(row for row in response.data["stores"] if row["id"] == self.store_a.pk)
        self.assertFalse(store_a["is_receiving"])
        self.assertTrue(store_a["is_entitled"])

    def test_shared_device_one_time_link_claim_and_authority_loss(self):
        request_response = self.client.post(
            "/api/work/shared-links/",
            {
                "device_key": str(uuid.uuid4()),
                "label": "Front shared phone",
                "platform": "android",
            },
            format="json",
        )
        self.assertEqual(request_response.status_code, 201)
        request_id = request_response.data["request_id"]
        claim_secret = request_response.data["claim_secret"]

        pending = self.client.post(
            f"/api/work/shared-links/{request_id}/claim/",
            {"claim_secret": claim_secret},
            format="json",
        )
        self.assertEqual(pending.status_code, 202)

        self.client.force_login(self.manager)
        approved = self.client.post(
            "/api/op/work-devices/approve/",
            {"code": request_response.data["code"], "store_ids": [self.store_a.pk]},
            format="json",
        )
        self.assertEqual(approved.status_code, 200)
        self.client.logout()

        claimed = self.client.post(
            f"/api/work/shared-links/{request_id}/claim/",
            {"claim_secret": claim_secret},
            format="json",
        )
        self.assertEqual(claimed.status_code, 200)
        token = claimed.data["token"]
        device_client = self.device_client(token)
        self.assertEqual(device_client.get("/api/work/me/").status_code, 200)

        group_membership = OperationGroupMembership.objects.get(
            operation_group=self.group, user=self.manager
        )
        group_membership.is_active = False
        group_membership.save(update_fields=["is_active", "updated_at"])
        me = device_client.get("/api/work/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data["stores"], [])
        self.assertEqual(device_client.get("/api/work/calls/").data["calls"], [])

        reused = self.client.post(
            f"/api/work/shared-links/{request_id}/claim/",
            {"claim_secret": claim_secret},
            format="json",
        )
        self.assertEqual(reused.status_code, 400)

    def test_other_group_manager_cannot_approve_code_for_foreign_store(self):
        link = self.client.post(
            "/api/work/shared-links/",
            {
                "device_key": str(uuid.uuid4()),
                "label": "Shared",
                "platform": "ios",
            },
            format="json",
        )
        self.client.force_login(self.outsider)
        response = self.client.post(
            "/api/op/work-devices/approve/",
            {"code": link.data["code"], "store_ids": [self.store_a.pk]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_pause_revoke_and_token_rotation(self):
        login = self.personal_login(store_ids=[self.store_a.pk])
        token = login.data["token"]
        device_id = login.data["device"]["id"]
        device_client = self.device_client(token)
        rotated = device_client.post("/api/work/token/rotate/", {}, format="json")
        self.assertEqual(rotated.status_code, 200)
        self.assertEqual(device_client.get("/api/work/me/").status_code, 403)
        new_client = self.device_client(rotated.data["token"])
        self.assertEqual(new_client.get("/api/work/me/").status_code, 200)

        self.client.force_login(self.manager)
        paused = self.client.post(
            f"/api/op/work-devices/{device_id}/action/",
            {"action": "pause"},
            format="json",
        )
        self.assertEqual(paused.status_code, 200)
        self.assertEqual(new_client.get("/api/work/calls/").data["calls"], [])
        revoked = self.client.post(
            f"/api/op/work-devices/{device_id}/action/",
            {"action": "revoke"},
            format="json",
        )
        self.assertEqual(revoked.status_code, 200)
        self.assertEqual(new_client.get("/api/work/me/").status_code, 403)
        resumed = self.client.post(
            f"/api/op/work-devices/{device_id}/action/",
            {"action": "resume"},
            format="json",
        )
        self.assertEqual(resumed.status_code, 400)
        self.assertEqual(WorkDevice.objects.get(pk=device_id).status, WorkDevice.Status.REVOKED)

    def test_heartbeat_updates_last_connection(self):
        login = self.personal_login(store_ids=[self.store_a.pk])
        client = self.device_client(login.data["token"])
        before = timezone.now()
        response = client.post("/api/work/heartbeat/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        device = WorkDevice.objects.get(pk=login.data["device"]["id"])
        self.assertGreaterEqual(device.last_seen_at, before)
