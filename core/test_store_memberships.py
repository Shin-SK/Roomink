from datetime import timedelta
from importlib import import_module
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection, close_old_connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Customer, Store, StoreInvitation, StoreMembership, StoreMembershipEvent, UserProfile
from core.services.order_policy import can_modify_business_datetime

User = get_user_model()


class StoreMembershipTest(TestCase):
    def setUp(self):
        self.a = Store.objects.create(name="テストA店")
        self.b = Store.objects.create(name="テストB店")
        self.c = Store.objects.create(name="テストC店")
        self.owner = self.user("owner-a", self.a, "manager")
        self.manager = self.user("owner-b", self.b, "manager")
        self.staff = self.user("staff-c", self.c, "staff")
        self.client = self.client_for(self.owner, self.a)
        self.b_client = self.client_for(self.manager, self.b)

    def user(self, name, store, role):
        user = User.objects.create_user(name, password="Membership-test-pass-77")
        UserProfile.objects.create(user=user, store=store, role=role)
        return user

    def client_for(self, user, store=None):
        client = APIClient()
        client.force_authenticate(user)
        if store:
            client.credentials(HTTP_X_ROOMINK_STORE=str(store.pk))
        return client

    def invite(self, role="staff"):
        response = self.b_client.post("/api/op/store-invitations/", {"username": self.owner.username, "role": role}, format="json")
        self.assertEqual(response.status_code, 202, response.data)
        return StoreInvitation.objects.get(recipient=self.owner, store=self.b, status="pending")

    def respond(self, invite, action="accept", client=None):
        return (client or self.client).post(f"/api/auth/store-invitations/{invite.pk}/respond/", {"action": action}, format="json")

    def test_existing_profiles_get_membership_and_password_is_unchanged(self):
        self.assertEqual(StoreMembership.objects.get(user=self.owner, store=self.a).role, "manager")
        self.assertTrue(self.owner.check_password("Membership-test-pass-77"))
        self.assertEqual(self.client.get("/api/auth/me/").data["store_id"], self.a.pk)

    def test_invitation_does_not_grant_access_until_recipient_accepts(self):
        invite = self.invite()
        b = self.client_for(self.owner, self.b)
        self.assertEqual(b.get("/api/customers/").status_code, 403)
        response = self.respond(invite)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(b.get("/api/customers/").status_code, 200)
        self.assertEqual(b.get("/api/auth/me/").data["role"], "staff")
        self.assertEqual(b.get("/api/staffs/").status_code, 403)
        self.assertEqual(self.client.get("/api/staffs/").status_code, 200)
        self.assertEqual(b.get("/api/auth/me/").data["password_policy"]["min_length"], 10)

    def test_acceptance_is_recipient_bound(self):
        invite = self.invite()
        self.assertEqual(self.respond(invite, client=self.b_client).status_code, 404)
        self.assertFalse(StoreMembership.objects.filter(user=self.owner, store=self.b).exists())

    def test_duplicate_invite_and_acceptance_are_idempotent(self):
        first = self.invite()
        second = self.invite(role="manager")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.role, "staff")
        self.assertEqual(self.respond(first).status_code, 200)
        self.assertEqual(self.respond(first).status_code, 200)
        self.assertEqual(StoreMembership.objects.filter(user=self.owner, store=self.b).count(), 1)
        self.assertEqual(StoreMembershipEvent.objects.filter(user=self.owner, action="invite_accepted").count(), 1)

    def test_declined_and_expired_invites_do_not_grant(self):
        invite = self.invite()
        self.assertEqual(self.respond(invite, "decline").status_code, 200)
        self.assertEqual(self.respond(invite).status_code, 400)
        expired = self.invite()
        expired.expires_at = timezone.now() - timedelta(seconds=1)
        expired.save(update_fields=["expires_at"])
        self.assertEqual(self.respond(expired).status_code, 400)
        fresh = self.invite()
        self.assertNotEqual(fresh.pk, expired.pk)

    def test_inviter_must_still_be_an_active_manager(self):
        invite = self.invite()
        StoreMembership.objects.filter(user=self.manager, store=self.b).update(role="staff")
        self.assertEqual(self.respond(invite).status_code, 403)
        self.assertFalse(StoreMembership.objects.filter(user=self.owner, store=self.b).exists())

    def test_disabled_inviter_cannot_grant_membership(self):
        invite = self.invite()
        self.manager.is_active = False
        self.manager.save()
        self.assertEqual(self.respond(invite).status_code, 403)

    def test_staff_cannot_invite_and_manager_cannot_target_unowned_store(self):
        staff = self.client_for(self.staff, self.c)
        self.assertEqual(staff.post("/api/op/store-invitations/", {"username": self.owner.username}).status_code, 403)
        self.assertEqual(self.client_for(self.owner, self.b).post("/api/op/store-invitations/", {"username": self.staff.username}).status_code, 403)
        self.assertEqual(self.b_client.post("/api/op/store-invitations/", {"username": self.owner.username, "role": "superuser"}).status_code, 400)

    def test_revoke_is_store_scoped(self):
        invite = self.invite()
        path = f"/api/op/store-invitations/{invite.pk}/revoke/"
        self.assertEqual(self.client.post(path).status_code, 404)
        self.assertEqual(self.b_client.post(path).status_code, 200)
        self.assertEqual(self.respond(invite).status_code, 400)

    def test_customer_cast_and_nonexistent_accounts_are_not_invited(self):
        cast = self.user("test-cast", self.c, "cast")
        for name in [cast.username, "does-not-exist"]:
            result = self.b_client.post("/api/op/store-invitations/", {"username": name}, format="json")
            self.assertEqual(result.status_code, 202)
        self.assertEqual(StoreInvitation.objects.count(), 0)

    def test_customer_data_and_exports_are_scoped(self):
        self.respond(self.invite())
        Customer.objects.create(store=self.a, display_name="Customer-A", phone="09000000001")
        Customer.objects.create(store=self.b, display_name="Customer-B", phone="09000000002")
        b = self.client_for(self.owner, self.b)
        result = b.get("/api/customers/")
        self.assertContains(result, "Customer-B")
        self.assertNotContains(result, "Customer-A")
        export = self.client_for(self.owner).get(f"/api/op/customers-export.csv?_store={self.b.pk}")
        self.assertEqual(export.status_code, 403)  # B staff cannot export.
        StoreMembership.objects.filter(user=self.owner, store=self.b).update(role="manager")
        export = self.client_for(self.owner).get(f"/api/op/customers-export.csv?_store={self.b.pk}")
        self.assertContains(export, "Customer-B")
        self.assertNotContains(export, "Customer-A")
        self.assertEqual(self.client.get(f"/api/op/customers-export.csv?_store={self.b.pk}").status_code, 403)
        self.assertEqual(self.client_for(self.owner, self.c).get("/api/customers/").status_code, 403)

    def test_invalid_store_selection_fails_closed(self):
        for raw in ["-1", "abc", "1 OR 1", "９", "9" * 100]:
            self.client.credentials(HTTP_X_ROOMINK_STORE=raw)
            self.assertEqual(self.client.get("/api/customers/").status_code, 403)

    def test_store_role_applies_to_past_orders(self):
        self.respond(self.invite())
        past = timezone.now() - timedelta(days=2)
        self.assertTrue(can_modify_business_datetime(self.owner, past, self.a))
        self.assertFalse(can_modify_business_datetime(self.owner, past, self.b))

    def test_multi_store_user_password_and_email_cannot_be_changed_by_store_manager(self):
        self.respond(self.invite())
        path = f"/api/staffs/{self.owner.profile.pk}/"
        response = self.b_client.patch(path, {"password": "Unwanted-password-444"}, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self.b_client.patch(path, {"email": "changed@example.invalid"}).status_code, 400)
        self.assertEqual(self.b_client.patch(path, {"role": "manager"}).status_code, 200)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.check_password("Membership-test-pass-77"))

    def test_remove_membership_keeps_other_stores_and_login(self):
        invitation = self.invite()
        self.respond(invitation)
        path = f"/api/staffs/{self.owner.profile.pk}/"
        self.assertEqual(self.b_client.delete(path).status_code, 204)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active)
        self.assertEqual(self.client.get("/api/customers/").status_code, 200)
        self.assertEqual(self.client_for(self.owner, self.b).get("/api/customers/").status_code, 403)
        self.assertEqual(self.respond(invitation).status_code, 200)
        self.assertEqual(self.client_for(self.owner, self.b).get("/api/customers/").status_code, 403)

    def test_final_membership_removed_user_can_still_receive_invitation(self):
        other = self.user("removed-staff", self.b, "staff")
        self.assertEqual(self.b_client.delete(f"/api/staffs/{other.profile.pk}/").status_code, 204)
        own_client = self.client_for(other)
        self.assertEqual(own_client.get("/api/auth/me/").data["role"], "unassigned")
        self.assertEqual(own_client.get("/api/customers/").status_code, 403)
        self.assertEqual(own_client.get("/api/auth/store-access/").status_code, 200)
        self.b_client.post("/api/op/store-invitations/", {"username": other.username})
        invite = StoreInvitation.objects.get(recipient=other, status="pending")
        self.assertEqual(self.respond(invite, client=own_client).status_code, 200)

    def test_last_manager_cannot_be_demoted(self):
        response = self.b_client.patch(f"/api/staffs/{self.manager.profile.pk}/", {"role": "staff"})
        self.assertEqual(response.status_code, 400)

    def test_single_store_avatar_update_response_matches_saved_value(self):
        response = self.client_for(self.staff, self.c)
        manager = self.user("manager-c", self.c, "manager")
        changed = self.client_for(manager, self.c).patch(
            f"/api/staffs/{self.staff.profile.pk}/", {"avatar_url": "https://example.com/avatar.png"},
        )
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertEqual(changed.data["avatar_url"], "https://example.com/avatar.png")
        self.staff.refresh_from_db()  # force_authenticate reuses the in-memory user.
        self.assertEqual(response.get("/api/auth/me/").data["avatar_url"], changed.data["avatar_url"])

    def test_invalid_store_cannot_mutate_profile_before_access_check(self):
        client = self.client_for(self.owner, self.c)
        response = client.patch("/api/auth/profile/", {"display_name": "must-not-save"})
        self.assertEqual(response.status_code, 403)
        self.owner.refresh_from_db()
        self.assertNotEqual(self.owner.first_name, "must-not-save")

    def test_deleting_original_store_preserves_membership_in_other_store(self):
        self.respond(self.invite())
        self.a.delete()
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active)
        result = self.client_for(self.owner).get("/api/auth/me/")
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data["store_id"], self.b.pk)

    def test_demotion_revokes_outstanding_invitations(self):
        invite = self.invite()
        replacement = self.user("replacement-b", self.b, "manager")
        client = self.client_for(replacement, self.b)
        self.assertEqual(client.patch(f"/api/staffs/{self.manager.profile.pk}/", {"role": "staff"}).status_code, 200)
        self.assertEqual(self.respond(invite).status_code, 400)

    def test_stale_store_header_does_not_prevent_invitation_inbox(self):
        self.invite()
        stale = self.client_for(self.owner, self.c)
        self.assertEqual(stale.get("/api/auth/me/").status_code, 403)
        self.assertEqual(len(stale.get("/api/auth/store-access/").data["invitations"]), 1)

    def test_invitation_acceptance_requires_csrf_even_with_valid_session(self):
        invite = self.invite()
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.owner)
        client.credentials(HTTP_X_ROOMINK_STORE=str(self.c.pk))
        self.assertEqual(self.respond(invite, client=client).status_code, 403)
        inbox = client.get("/api/auth/store-access/")
        client.credentials(HTTP_X_CSRFTOKEN=inbox.data["csrf_token"], HTTP_X_ROOMINK_STORE=str(self.c.pk))
        self.assertEqual(self.respond(invite, client=client).status_code, 200)

    def test_migration_backfills_existing_users_without_changing_password(self):
        StoreMembership.objects.all().delete()
        password_hash = self.owner.password
        migration = import_module("core.migrations.0081_store_memberships_and_invitations")
        migration.migrate_operator_memberships(apps, connection.schema_editor())
        self.assertEqual(StoreMembership.objects.filter(user=self.owner, store=self.a).count(), 1)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.password, password_hash)


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class MembershipConcurrencyTest(TransactionTestCase):
    def test_concurrent_self_demotions_cannot_remove_last_manager(self):
        store = Store.objects.create(name="Concurrent test store")
        users = [User.objects.create_user(f"concurrent-manager-{i}") for i in range(2)]
        profiles = [UserProfile.objects.create(user=u, store=store, role="manager") for u in users]
        barrier = Barrier(2)

        def demote(index):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(User.objects.get(pk=users[index].pk))
                client.credentials(HTTP_X_ROOMINK_STORE=str(store.pk))
                barrier.wait(timeout=10)
                return client.patch(f"/api/staffs/{profiles[index].pk}/", {"role": "staff"}).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(demote, [0, 1]))
        self.assertEqual(sorted(results), [200, 400])
        self.assertEqual(StoreMembership.objects.filter(store=store, role="manager", is_active=True).count(), 1)
