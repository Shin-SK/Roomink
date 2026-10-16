from datetime import date, datetime, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Cast, Room, ShiftAssignment, ShiftConfirmNotificationLog, Store, UserProfile


class TimelineShiftConfirmationTest(TestCase):
    def setUp(self):
        self.day = date(2026, 10, 16)
        self.now = datetime(2026, 10, 16, 14, tzinfo=ZoneInfo("Asia/Tokyo"))
        self.store = Store.objects.create(name="確認店舗", timezone="Asia/Tokyo")
        self.room = Room.objects.create(store=self.store, name="確認ルーム")
        self.manager = self.user("manager", self.store)
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def user(self, role, store):
        user = get_user_model().objects.create(username=f"{role}-{store.pk}", password="!")
        UserProfile.objects.create(user=user, store=store, role=role)
        return user

    def shift(self, name="未確認", **kwargs):
        cast = Cast.objects.create(store=self.store, name=name)
        values = dict(store=self.store, cast=cast, room=self.room, date=self.day,
                      start_time=time(15), end_time=time(20))
        values.update(kwargs)
        return ShiftAssignment.objects.create(**values)

    def alerts(self, now=None, day=None, client=None):
        with patch("core.views.timezone.now", return_value=now or self.now):
            return (client or self.client).get(
                f"/api/op/shift-confirm-alerts/?date={day or self.day}"
            )

    def test_one_hour_boundary_is_exact_not_rounded_down(self):
        shift = self.shift()
        before = self.alerts(self.now - timedelta(seconds=1)).json()["alerts"]
        at = self.alerts().json()["alerts"]
        self.assertEqual(before[0]["alert_level"], "TWO_HOURS")
        self.assertEqual(at[0]["alert_level"], "ONE_HOUR")
        self.assertEqual(at[0]["shift_id"], shift.pk)
        self.assertEqual(at[0]["start_time_extended"], "15:00")
        self.assertFalse(at[0]["has_started"])

    def test_confirmed_absent_ended_and_other_dates_are_excluded(self):
        wanted = self.shift()
        self.shift("確認済", confirmed_at=self.now)
        self.shift("当欠", is_absent=True)
        self.shift("終了済", start_time=time(10), end_time=time(14))
        self.shift("前日", date=self.day - timedelta(days=1))
        self.shift("翌日", date=self.day + timedelta(days=1))
        self.assertEqual([a["shift_id"] for a in self.alerts().json()["alerts"]], [wanted.pk])

    def test_confirmation_removes_alert_on_next_read_without_sending(self):
        shift = self.shift()
        self.assertEqual(len(self.alerts().json()["alerts"]), 1)
        shift.confirmed_at = self.now
        shift.save(update_fields=["confirmed_at"])
        result = self.alerts().json()
        self.assertEqual(result["alerts"], [])
        self.assertFalse(result["external_send_supported"])
        self.assertEqual(ShiftConfirmNotificationLog.objects.count(), 0)

    def test_started_shift_remains_until_end(self):
        self.shift(start_time=time(13), end_time=time(15))
        alert = self.alerts().json()["alerts"][0]
        self.assertTrue(alert["has_started"])
        self.assertEqual(self.alerts(self.now + timedelta(hours=1)).json()["alerts"], [])

    def test_overnight_shift_uses_actual_date_and_extended_label(self):
        self.shift(start_time=time(1), start_day_offset=1, end_time=time(4), end_day_offset=1)
        midnight = datetime(2026, 10, 17, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
        self.assertEqual(self.alerts(midnight - timedelta(seconds=1)).json()["alerts"][0]["alert_level"], "TWO_HOURS")
        alert = self.alerts(midnight).json()["alerts"][0]
        self.assertEqual(alert["alert_level"], "ONE_HOUR")
        self.assertEqual(alert["start_time_extended"], "25:00")
        self.assertFalse(alert["has_started"])
        self.assertEqual(self.alerts(midnight, day=date(2026, 10, 17)).json()["alerts"], [])

    def test_multiple_shifts_are_independent_and_store_timezone_is_used(self):
        first = self.shift(confirmed_at=self.now)
        second = self.shift("別シフト", cast=first.cast, start_time=time(14, 30))
        self.store.timezone = "Asia/Singapore"
        self.store.save(update_fields=["timezone"])
        # Tokyo 14:00 is Singapore 13:00: 14:30 is still 90 minutes away.
        alert = self.alerts().json()["alerts"][0]
        self.assertEqual(alert["shift_id"], second.pk)
        self.assertEqual(alert["alert_level"], "TWO_HOURS")

    def test_store_and_role_boundaries(self):
        self.shift()
        other = Store.objects.create(name="他店舗")
        other_client = APIClient()
        other_client.force_authenticate(self.user("manager", other))
        self.assertEqual(self.alerts(client=other_client).json()["alerts"], [])
        self.assertEqual(other_client.get(
            f"/api/op/shift-confirm-alerts/?date={self.day}", HTTP_X_ROOMINK_STORE=str(self.store.pk)
        ).status_code, 403)
        for role in ("staff", "cast"):
            client = APIClient()
            client.force_authenticate(self.user(role, self.store))
            response = self.alerts(client=client)
            self.assertEqual(response.status_code, 200 if role == "staff" else 403)
        self.assertEqual(self.alerts(client=APIClient()).status_code, 403)

    def test_bad_date_returns_validation_error(self):
        for value in ("", "2026-02-30", "not-a-date"):
            self.assertEqual(self.client.get(
                "/api/op/shift-confirm-alerts/", {"date": value}
            ).status_code, 400)
