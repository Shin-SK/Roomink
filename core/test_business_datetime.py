from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from core.services.business_datetime import (
    BusinessDateTimeError,
    build_business_interval,
    build_store_datetime,
    business_date_for_datetime,
    business_day_range,
    format_extended_time,
    intervals_overlap,
    parse_extended_time,
)


class ExtendedTimeTest(SimpleTestCase):
    def test_parse_normal_and_extended_times(self):
        cases = {
            "00:00": (time(0, 0), 0),
            "23:59": (time(23, 59), 0),
            "24:00": (time(0, 0), 1),
            "25:30": (time(1, 30), 1),
            "29:00": (time(5, 0), 1),
        }

        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(parse_extended_time(value), expected)

    def test_parse_rejects_invalid_or_over_limit_values(self):
        for value in ("", "9:00", "24", "23:60", "29:01", "30:00", "-1:00", None):
            with self.subTest(value=value):
                with self.assertRaises(BusinessDateTimeError):
                    parse_extended_time(value)

    def test_parse_supports_an_injected_future_limit(self):
        self.assertEqual(
            parse_extended_time("30:00", max_extended_hour=30),
            (time(6, 0), 1),
        )

    def test_format_normal_and_extended_times(self):
        self.assertEqual(format_extended_time(time(23, 59), 0), "23:59")
        self.assertEqual(format_extended_time(time(0, 0), 1), "24:00")
        self.assertEqual(format_extended_time(time(5, 0), 1), "29:00")

    def test_format_rejects_lossy_or_invalid_values(self):
        for local_time, day_offset in (
            (time(5, 0, 1), 1),
            (time(5, 0), 2),
            (time(5, 1), 1),
        ):
            with self.subTest(local_time=local_time, day_offset=day_offset):
                with self.assertRaises(BusinessDateTimeError):
                    format_extended_time(local_time, day_offset)


class BusinessDateTimeTest(SimpleTestCase):
    tokyo = "Asia/Tokyo"

    def test_build_store_datetime_uses_business_date_and_offset(self):
        value = build_store_datetime(
            date(2026, 7, 31),
            time(5, 0),
            day_offset=1,
            timezone_name=self.tokyo,
        )

        self.assertEqual(value.isoformat(), "2026-08-01T05:00:00+09:00")

    def test_build_business_interval_supports_overnight_shift(self):
        start_at, end_at = build_business_interval(
            date(2026, 7, 31),
            time(23, 0),
            time(5, 0),
            start_day_offset=0,
            end_day_offset=1,
            timezone_name=self.tokyo,
        )

        self.assertEqual(start_at.isoformat(), "2026-07-31T23:00:00+09:00")
        self.assertEqual(end_at.isoformat(), "2026-08-01T05:00:00+09:00")
        self.assertEqual(end_at - start_at, timedelta(hours=6))

    def test_build_business_interval_requires_positive_duration(self):
        for end_time, end_offset in ((time(11, 0), 0), (time(10, 0), 0)):
            with self.subTest(end_time=end_time, end_offset=end_offset):
                with self.assertRaises(BusinessDateTimeError):
                    build_business_interval(
                        date(2026, 7, 31),
                        time(11, 0),
                        end_time,
                        start_day_offset=0,
                        end_day_offset=end_offset,
                        timezone_name=self.tokyo,
                    )

    def test_business_date_boundary_is_start_inclusive(self):
        before = datetime(2026, 8, 1, 4, 59, tzinfo=ZoneInfo(self.tokyo))
        boundary = datetime(2026, 8, 1, 5, 0, tzinfo=ZoneInfo(self.tokyo))

        self.assertEqual(
            business_date_for_datetime(before, self.tokyo, boundary_hour=5),
            date(2026, 7, 31),
        )
        self.assertEqual(
            business_date_for_datetime(boundary, self.tokyo, boundary_hour=5),
            date(2026, 8, 1),
        )

    def test_business_date_converts_from_source_timezone(self):
        utc_value = datetime(2026, 7, 31, 19, 30, tzinfo=timezone.utc)

        self.assertEqual(
            business_date_for_datetime(utc_value, self.tokyo, boundary_hour=5),
            date(2026, 7, 31),
        )

    def test_business_day_range_is_half_open(self):
        start_at, end_at = business_day_range(
            date(2026, 7, 31),
            self.tokyo,
            boundary_hour=5,
        )

        self.assertEqual(start_at.isoformat(), "2026-07-31T05:00:00+09:00")
        self.assertEqual(end_at.isoformat(), "2026-08-01T05:00:00+09:00")

    def test_business_date_rejects_naive_datetime(self):
        with self.assertRaises(BusinessDateTimeError):
            business_date_for_datetime(
                datetime(2026, 8, 1, 4, 59),
                self.tokyo,
                boundary_hour=5,
            )

    def test_invalid_timezone_is_rejected(self):
        with self.assertRaises(BusinessDateTimeError):
            build_store_datetime(
                date(2026, 7, 31),
                time(11, 0),
                timezone_name="Invalid/Timezone",
            )

    def test_nonexistent_dst_local_time_is_rejected(self):
        with self.assertRaises(BusinessDateTimeError):
            build_store_datetime(
                date(2026, 3, 8),
                time(2, 30),
                timezone_name="America/New_York",
            )

    def test_ambiguous_dst_local_time_is_rejected(self):
        with self.assertRaises(BusinessDateTimeError):
            build_store_datetime(
                date(2026, 11, 1),
                time(1, 30),
                timezone_name="America/New_York",
            )

    def test_business_day_range_preserves_dst_duration(self):
        start_at, end_at = business_day_range(
            date(2026, 3, 8),
            "America/New_York",
            boundary_hour=0,
        )

        self.assertEqual(
            end_at.astimezone(timezone.utc) - start_at.astimezone(timezone.utc),
            timedelta(hours=23),
        )


class IntervalOverlapTest(SimpleTestCase):
    def setUp(self):
        self.base = datetime(2026, 7, 31, 10, 0, tzinfo=timezone.utc)

    def test_intersecting_intervals_overlap(self):
        self.assertTrue(
            intervals_overlap(
                self.base,
                self.base + timedelta(hours=2),
                self.base + timedelta(hours=1),
                self.base + timedelta(hours=3),
            )
        )

    def test_touching_half_open_intervals_do_not_overlap(self):
        self.assertFalse(
            intervals_overlap(
                self.base,
                self.base + timedelta(hours=1),
                self.base + timedelta(hours=1),
                self.base + timedelta(hours=2),
            )
        )

    def test_contained_interval_overlaps(self):
        self.assertTrue(
            intervals_overlap(
                self.base,
                self.base + timedelta(hours=4),
                self.base + timedelta(hours=1),
                self.base + timedelta(hours=2),
            )
        )

    def test_invalid_interval_is_rejected(self):
        with self.assertRaises(BusinessDateTimeError):
            intervals_overlap(
                self.base,
                self.base,
                self.base + timedelta(hours=1),
                self.base + timedelta(hours=2),
            )
