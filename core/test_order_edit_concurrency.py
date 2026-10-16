from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from core.models import Cast, Course, Customer, Option, Order, OrderEditLog, Room, Store, UserProfile
from core.serializers import OrderUpdateSerializer


@override_settings(SMS_DUMMY_MODE=True)
class OrderEditConcurrencyTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="編集テスト店")
        self.cast_user, self.cast_client = self.client_for("cast", self.store, "cast")
        self.manager, self.operator = self.client_for("manager", self.store, "manager")
        self.staff, self.staff_client = self.client_for("staff", self.store, "staff")
        self.cast = Cast.objects.create(store=self.store, name="テスト", user=self.cast_user)
        self.course = Course.objects.create(store=self.store, name="60分", duration=60, price=20000)
        self.room = Room.objects.create(store=self.store, name="A")
        customer = Customer.objects.create(store=self.store, phone="09000000000")
        start = timezone.now().replace(second=0, microsecond=0)
        self.order = Order.objects.create(
            store=self.store, cast=self.cast, course=self.course, customer=customer, room=self.room,
            start=start, end=start + timedelta(minutes=60), status="CONFIRMED", payment_method="CASH",
            course_name=self.course.name, course_price=20000, total_price=20000,
        )
        self.option = Option.objects.create(store=self.store, name="追加", price=2000)
        self.url = f"/api/orders/{self.order.pk}/"
        self.cast_url = f"/api/cast/orders/{self.order.pk}/options/"

    def client_for(self, name, store, role):
        user = get_user_model().objects.create_user(name)
        UserProfile.objects.create(user=user, store=store, role=role)
        client = APIClient()
        client.force_authenticate(user)
        return user, client

    def version(self):
        return self.operator.get(self.url).data["updated_at"]

    def change(self, **fields):
        return self.operator.patch(self.url, {"expected_updated_at": self.version(), **fields}, format="json")

    def assert_option(self, amount=2000):
        self.order.refresh_from_db()
        self.assertEqual(list(self.order.options.values_list("id", flat=True)), [self.option.pk])
        self.assertEqual(self.order.options_price, amount)
        self.assertEqual(self.order.total_price, 20000 + amount)

    def test_add_and_include_options_on_card_survives_reload_and_payment_only_save(self):
        response = self.change(options=[self.option.pk], payment_method="CARD", card_include_options=True)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["option_ids"], [self.option.pk])
        response = self.change(payment_method="CASH")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["card_include_options"])
        self.assert_option()
        self.assertEqual(self.operator.get(self.url).data["options_price"], 2000)

    def test_stale_operator_cannot_remove_added_option_or_change_payment(self):
        old = self.version()
        self.assertEqual(self.change(options=[self.option.pk]).status_code, 200)
        response = self.operator.patch(self.url, {
            "options": [], "payment_method": "CARD", "expected_updated_at": old,
        }, format="json")
        self.assertEqual(response.status_code, 409, response.data)
        self.assert_option()
        self.assertEqual(self.order.payment_method, "CASH")
        self.assertEqual(OrderEditLog.objects.count(), 1)

    def test_cast_and_operator_detect_each_others_changes(self):
        old = self.version()
        self.change(options=[self.option.pk])
        response = self.cast_client.post(self.cast_url, {"option_ids": [], "expected_updated_at": old}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assert_option()
        current = self.version()
        response = self.cast_client.post(self.cast_url, {"option_ids": [], "expected_updated_at": current}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn("updated_at", response.data)
        response = self.operator.patch(self.url, {"options": [self.option.pk], "expected_updated_at": current}, format="json")
        self.assertEqual(response.status_code, 409)
        self.order.refresh_from_db()
        self.assertEqual(self.order.options_price, 0)

    def test_old_clients_without_version_cannot_overwrite_options(self):
        self.change(options=[self.option.pk])
        for client, url, payload in (
            (self.operator, self.url, {"options": []}),
            (self.cast_client, self.cast_url, {"option_ids": []}),
        ):
            request = client.patch if url == self.url else client.post
            response = request(url, payload, format="json")
            self.assertEqual(response.status_code, 409, response.data)
        self.assert_option()

    def test_intentional_delete_with_current_version_is_recorded(self):
        self.change(options=[self.option.pk])
        response = self.change(options=[])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_price"], 20000)
        log = OrderEditLog.objects.latest("id")
        self.assertEqual(log.before["option_ids"], [self.option.pk])
        self.assertEqual(log.after["option_ids"], [])

    def test_payment_waiting_for_lock_uses_latest_amount_not_stale_snapshot(self):
        data = {"payment_method": "CARD", "card_include_options": True}
        request = APIRequestFactory().patch("/", data, format="json")
        force_authenticate(request, self.manager)
        serializer = OrderUpdateSerializer(
            Order.objects.prefetch_related("options").get(pk=self.order.pk),
            data=data, partial=True, context={"request": Request(request, parsers=[JSONParser()])},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.change(options=[self.option.pk])
        serializer.save(updated_by=self.manager)
        self.assert_option()
        self.assertEqual(self.order.payment_method, "CARD")

    def test_request_validated_before_completion_cannot_reopen_order(self):
        serializer = OrderUpdateSerializer(self.order, data={"memo": "late"}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        Order.objects.filter(pk=self.order.pk).update(status="DONE")
        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            serializer.save()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "DONE")
        self.assertEqual(self.order.memo, "")

    def test_audit_contains_actor_and_amounts_but_no_customer_or_memo(self):
        self.change(options=[self.option.pk], memo="private note")
        log = OrderEditLog.objects.get()
        self.assertEqual(log.acted_by, self.manager)
        self.assertEqual(log.store, self.store)
        self.assertEqual(log.source, "operator")
        self.assertEqual(log.before["total_price"], 20000)
        self.assertEqual(log.after["total_price"], 22000)
        self.assertNotIn("memo", log.after)
        self.assertNotIn("customer", log.after)

    def test_cast_change_is_audited_and_metadata_only_change_is_not(self):
        response = self.cast_client.post(self.cast_url, {
            "option_ids": [self.option.pk], "expected_updated_at": self.version(),
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        log = OrderEditLog.objects.get()
        self.assertEqual(log.acted_by, self.cast_user)
        self.assertEqual(log.source, "cast")
        self.change(memo="note")
        self.assertEqual(OrderEditLog.objects.count(), 1)

    def test_audit_failure_rolls_back_money_and_options(self):
        with patch("core.services.order_editing.OrderEditLog.objects.create", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.change(options=[self.option.pk])
        self.order.refresh_from_db()
        self.assertEqual(self.order.options.count(), 0)
        self.assertEqual(self.order.total_price, 20000)

    def test_staff_can_edit_current_order_and_other_roles_or_stores_cannot(self):
        response = self.staff_client.patch(self.url, {"options": [self.option.pk], "expected_updated_at": self.version()}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.cast_client.patch(self.url, {"options": []}, format="json").status_code, 403)
        other = Store.objects.create(name="別店舗")
        _, outsider = self.client_for("outsider", other, "manager")
        self.assertEqual(outsider.patch(self.url, {"options": []}, format="json").status_code, 404)
        foreign = Option.objects.create(store=other, name="他店", price=100)
        self.assertEqual(self.change(options=[foreign.pk]).status_code, 400)
        self.assert_option()

    def test_stale_metadata_and_invalid_versions_do_not_partially_save(self):
        old = self.version()
        self.change(memo="new")
        response = self.operator.patch(self.url, {"memo": "old", "expected_updated_at": old}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.operator.get(self.url).data["memo"], "new")
        self.assertEqual(self.change(options=[self.option.pk], expected_updated_at="invalid").status_code, 400)

    def test_zero_price_options_still_use_conflict_protection(self):
        self.option.price = 0
        self.option.save()
        self.change(options=[self.option.pk])
        self.assert_option(0)
        self.assertEqual(OrderEditLog.objects.get().after["option_ids"], [self.option.pk])
