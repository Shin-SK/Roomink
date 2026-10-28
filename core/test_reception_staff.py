from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIClient

from core.models import CallLog, Order, OrderEditLog, Store, StoreMembership, UserProfile
from core.serializers import OrderCreateSerializer
from core.test_order_operator_tracking import OrderOperatorTrackingTest


@override_settings(SMS_DUMMY_MODE=True)
class ReceptionStaffTest(OrderOperatorTrackingTest):
    def payload(self, **extra):
        from datetime import timedelta
        return {"cast": self.cast.pk, "customer": self.customer.pk, "course": self.course.pk,
                "start": self.start.isoformat(), "end": (self.start + timedelta(hours=1)).isoformat(), **extra}

    def change(self, order, **extra):
        order.refresh_from_db()
        return self.client_as(self.manager).patch(f"/api/orders/{order.pk}/", {
            "expected_updated_at": order.updated_at.isoformat(), **extra,
        }, format="json")

    def test_explicit_receiver_is_independent_of_actor_and_survives_reload(self):
        response = self.client_as(self.staff).post("/api/orders/", self.payload(reception_staff=self.manager.pk), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(pk=response.data["id"])
        self.assertEqual(order.reception_staff, self.manager)
        self.assertEqual(order.created_by, self.staff)
        self.assertEqual(order.reception_staff_name, self.manager.username)
        data = self.client_as(self.staff).get(f"/api/orders/{order.pk}/").data
        self.assertEqual(data["reception_staff_name"], self.manager.username)
        self.assertEqual(data["created_by_name"], self.staff.username)

    def test_default_and_explicit_unknown(self):
        order = self.create_order()
        self.assertEqual(order.reception_staff, self.staff)
        self.assertEqual(self.change(order, reception_staff=None).status_code, 200)
        order.refresh_from_db()
        self.assertIsNone(order.reception_staff)
        self.assertEqual(order.reception_staff_name, "")
        self.assertEqual(order.created_by, self.staff)

    def test_correction_has_before_after_actor_timestamp_and_no_financial_change(self):
        order = self.create_order()
        before = (order.total_price, order.status, order.cast_id, order.start, order.end)
        response = self.change(order, reception_staff=self.manager.pk)
        self.assertEqual(response.status_code, 200, response.data)
        log = response.data["reception_staff_history"][0]
        self.assertEqual((log["before_name"], log["after_name"], log["acted_by_name"]),
                         (self.staff.username, self.manager.username, self.manager.username))
        self.assertTrue(log["created_at"])
        order.refresh_from_db()
        self.assertEqual(before, (order.total_price, order.status, order.cast_id, order.start, order.end))
        self.assertEqual(order.created_by, self.staff)
        self.assertEqual(self.change(order, memo="other edit").status_code, 200)
        self.assertEqual(OrderEditLog.objects.filter(order=order).count(), 1)

    def test_candidates_are_store_scoped_minimal_and_available_to_staff(self):
        foreign = Store.objects.create(name="別店舗")
        user = get_user_model().objects.create_user("foreign")
        UserProfile.objects.create(user=user, store=foreign, role="staff")
        for actor in (self.manager, self.staff):
            r = self.client_as(actor).get("/api/orders/reception-staffs/")
            self.assertEqual(r.status_code, 200, r.data)
            self.assertEqual({x["id"] for x in r.data["staffs"]}, {self.manager.pk, self.staff.pk})
            self.assertEqual(set(r.data["staffs"][0]), {"id", "name"})
            self.assertEqual(r.data["current_user"], actor.pk)

    def test_foreign_disabled_and_non_operator_are_denied_on_create_and_edit(self):
        order = self.create_order()
        foreign = Store.objects.create(name="別店舗")
        for name, store, role, active in (("foreign", foreign, "staff", True),
                                           ("inactive", self.store, "staff", False),
                                           ("cast", self.store, "cast", True)):
            user = get_user_model().objects.create_user(name, is_active=active)
            UserProfile.objects.create(user=user, store=store, role=role)
            r = self.client_as(self.staff).post("/api/orders/", self.payload(reception_staff=user.pk), format="json")
            self.assertEqual(r.status_code, 400, r.data)
            self.assertEqual(self.change(order, reception_staff=user.pk).status_code, 400)
        StoreMembership.objects.filter(user=self.manager).update(is_active=False)
        r = self.client_as(self.staff).get("/api/orders/reception-staffs/")
        self.assertEqual([x["id"] for x in r.data["staffs"]], [self.staff.pk])

    def test_stale_or_unversioned_receiver_edit_is_denied(self):
        order = self.create_order()
        old = order.updated_at.isoformat()
        self.assertEqual(self.change(order, memo="newer").status_code, 200)
        client = self.client_as(self.manager)
        for extra in ({}, {"expected_updated_at": old}):
            r = client.patch(f"/api/orders/{order.pk}/", {"reception_staff": self.manager.pk, **extra}, format="json")
            self.assertEqual(r.status_code, 409, r.data)
        order.refresh_from_db()
        self.assertEqual(order.reception_staff, self.staff)

    def test_audit_failure_rolls_back_receiver_and_actor(self):
        order = self.create_order()
        with patch("core.services.order_editing.OrderEditLog.objects.create", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.change(order, reception_staff=self.manager.pk)
        order.refresh_from_db()
        self.assertEqual(order.reception_staff, self.staff)
        self.assertEqual(order.updated_by, self.staff)

    def test_old_order_and_public_serializer_do_not_infer_receiver(self):
        serializer = OrderCreateSerializer(data=self.payload())
        self.assertTrue(serializer.is_valid(), serializer.errors)
        order = serializer.save()
        self.assertIsNone(order.reception_staff)
        self.assertEqual(order.reception_staff_name, "")
        serializer = OrderCreateSerializer(data=self.payload(reception_staff=self.staff.pk))
        from rest_framework.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            serializer.is_valid()

    def test_cti_candidates_and_creation_use_call_store(self):
        call = CallLog.objects.create(store=self.store, from_phone=self.customer.phone, to_phone="05000000000", contact_id="reception-fixture")
        client = self.client_as(self.staff)
        r = client.get("/api/orders/reception-staffs/", HTTP_X_ROOMINK_CALL=str(call.pk))
        self.assertEqual(r.status_code, 200, r.data)
        r = client.post("/api/orders/", self.payload(reception_staff=self.manager.pk), format="json", HTTP_X_ROOMINK_CALL=str(call.pk))
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["reception_staff"], self.manager.pk)

    def test_anonymous_and_cast_cannot_list_or_change(self):
        user = get_user_model().objects.create_user("cast_denied")
        UserProfile.objects.create(user=user, store=self.store, role="cast")
        order = self.create_order()
        for client in (APIClient(), self.client_as(user)):
            self.assertIn(client.get("/api/orders/reception-staffs/").status_code, (401, 403))
            self.assertIn(client.patch(f"/api/orders/{order.pk}/", {"reception_staff": self.manager.pk}, format="json").status_code, (401, 403))

    def test_membership_revoked_after_validation_is_checked_again_under_lock(self):
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory, force_authenticate
        from rest_framework.exceptions import ValidationError
        from core.serializers import OrderUpdateSerializer
        order = self.create_order()
        request = APIRequestFactory().patch('/')
        force_authenticate(request, self.staff)
        serializer = OrderUpdateSerializer(order, data={
            'reception_staff': self.manager.pk, 'expected_updated_at': order.updated_at.isoformat(),
        }, partial=True, context={'request': Request(request)})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        StoreMembership.objects.filter(user=self.manager).update(is_active=False)
        with self.assertRaises(ValidationError):
            serializer.save(updated_by=self.staff)
        order.refresh_from_db()
        self.assertEqual(order.reception_staff, self.staff)

    def test_deleted_receiver_name_and_original_actor_remain(self):
        order = self.create_order()
        self.assertEqual(self.change(order, reception_staff=self.manager.pk).status_code, 200)
        self.manager.delete()
        order.refresh_from_db()
        self.assertIsNone(order.reception_staff)
        self.assertEqual(order.reception_staff_name, 'tracking_manager')
        self.assertEqual(order.created_by, self.staff)

    def test_completed_and_cancelled_reservations_remain_locked(self):
        order = self.create_order()
        for state in ('DONE', 'CANCELLED'):
            Order.objects.filter(pk=order.pk).update(status=state)
            self.assertEqual(self.change(order, reception_staff=self.manager.pk).status_code, 400)
