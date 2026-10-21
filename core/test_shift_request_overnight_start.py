import csv
import io
from datetime import datetime, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import Area, Cast, CastAreaPreference, Room, ShiftAssignment, ShiftRequest, Store
from core.test_shift_request_extended_time import ShiftRequestExtendedTimeTest


class OvernightShiftRequestTest(ShiftRequestExtendedTimeTest):
    def request_overnight(self, **overrides):
        response = self.cast_client.post('/api/cast/shift-requests/', self.request_payload(
            start_time='00:00', start_day_offset=1, **overrides,
        ), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['start_time_extended'], '24:00')
        return response.data

    def earlier_shift(self):
        earlier = Cast.objects.create(store=self.store, name='前の時間帯')
        return ShiftAssignment.objects.create(
            store=self.store, cast=earlier, room=self.room, date=self.shift_date,
            start_time=time(14), end_time=time(0), end_day_offset=1,
        )

    def test_overnight_request_approval_and_export_round_trip(self):
        self.earlier_shift()
        request = self.request_overnight()
        response = self.manager_client.post(f"/api/op/shift-requests/{request['id']}/approve/", {
            'room': self.room.pk,
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['approved_start_time_extended'], '24:00')
        shift = ShiftAssignment.objects.get(cast=self.cast)
        self.assertEqual(shift.start_day_offset, 1)
        exported = self.manager_client.get('/api/op/shift-requests/export_csv/')
        row = next(csv.DictReader(io.StringIO(exported.content.decode('utf-8-sig'))))
        self.assertEqual(row['requested_start_time'], '24:00')
        self.assertEqual(row['approved_start_time'], '24:00')
        listed = self.cast_client.get('/api/cast/shift-requests/').data['results'][0]
        self.assertEqual(listed['approved_start_time_extended'], '24:00')

    def test_approval_can_change_daytime_request_to_overnight(self):
        self.earlier_shift()
        request = self.cast_client.post('/api/cast/shift-requests/', self.request_payload(), format='json').data
        response = self.manager_client.post(f"/api/op/shift-requests/{request['id']}/approve/", {
            'start_time': '00:00', 'start_day_offset': 1, 'room': self.room.pk,
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['approved_start_time_extended'], '24:00')

    def test_csv_preview_apply_and_replay(self):
        self.earlier_shift()
        request = self.request_overnight()
        row = dict(shift_request_id=request['id'], approved_date=self.shift_date.isoformat(),
                   approved_start_time='24:00', approved_end_time='29:00', approved_room_id=self.room.pk)
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
        response = self.manager_client.post('/api/op/shift-requests/import_preview/', {
            'file': SimpleUploadedFile('overnight.csv', output.getvalue().encode()),
        }, format='multipart')
        self.assertEqual(response.data['applicable_rows'], 1, response.data)
        response = self.manager_client.post('/api/op/shift-requests/import_apply/', {'rows': [row]}, format='json')
        self.assertEqual(response.data['applied_count'], 1, response.data)
        self.assertEqual(ShiftAssignment.objects.get(cast=self.cast).start_day_offset, 1)
        replay = self.manager_client.post('/api/op/shift-requests/import_apply/', {'rows': [row]}, format='json')
        self.assertEqual(replay.data['applied_count'], 0)
        self.assertEqual(ShiftAssignment.objects.filter(cast=self.cast).count(), 1)

    def test_overnight_bulk_and_overlap_and_patch(self):
        body = {'items': [dict(date=self.shift_date.isoformat(), start_time='00:00', start_day_offset=1,
                               end_time='05:00', end_day_offset=1)]}
        response = self.cast_client.post('/api/cast/shift-requests/bulk-create/', body, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        request = response.data['created'][0]
        self.assertEqual(request['start_time_extended'], '24:00')
        duplicate = self.cast_client.post('/api/cast/shift-requests/bulk-create/', body, format='json')
        self.assertEqual(duplicate.status_code, 400)
        patched = self.cast_client.patch(f"/api/cast/shift-requests/{request['id']}/", {'memo': '変更'}, format='json')
        self.assertEqual(patched.data['start_time_extended'], '24:00')

    def test_invalid_boundaries_and_forged_approval_fields(self):
        for start, offset in [('05:01', 1), ('00:00', 2), ('00:00', -1), ('00:00', 0)]:
            response = self.cast_client.post('/api/cast/shift-requests/', self.request_payload(
                start_time=start, start_day_offset=offset,
            ), format='json')
            self.assertEqual(response.status_code, 400, response.data)
        request = self.request_overnight(approved_start_day_offset=1)
        self.assertEqual(request['approved_start_day_offset'], 0)

    def test_real_overlap_and_other_store_room_are_denied(self):
        earlier = self.earlier_shift()
        earlier.end_time = time(1)
        earlier.save()
        request = self.request_overnight()
        other_room = Room.objects.create(store=Store.objects.create(name='別店舗'), name='別室')
        for room in [self.room.pk, other_room.pk]:
            response = self.manager_client.post(f"/api/op/shift-requests/{request['id']}/approve/", {'room': room}, format='json')
            self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(ShiftAssignment.objects.filter(cast=self.cast).exists())

    def test_area_assignment_uses_overnight_start(self):
        self.earlier_shift()
        area = Area.objects.create(store=self.store, name='深夜エリア')
        self.room.area = area
        self.room.save()
        CastAreaPreference.objects.create(cast=self.cast, area=area, rank=1)
        response = self.manager_client.post('/api/shifts/', dict(
            date=self.shift_date.isoformat(), cast=self.cast.pk, requested_area=area.pk,
            start_time='00:00', start_day_offset=1, end_time='05:00', end_day_offset=1,
        ), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['room'], self.room.pk)

    def test_cast_confirmation_and_schedule_keep_overnight_start(self):
        shift = ShiftAssignment.objects.create(
            store=self.store, cast=self.cast, room=self.room, date=self.shift_date,
            start_time=time(0), start_day_offset=1, end_time=time(5), end_day_offset=1,
        )
        daytime = ShiftAssignment.objects.create(
            store=self.store, cast=self.cast, room=self.room, date=self.shift_date,
            start_time=time(14), end_time=time(18),
        )
        with patch('core.views.timezone.now', return_value=datetime(2026, 8, 1, 12, tzinfo=ZoneInfo('Asia/Tokyo'))):
            first = self.cast_client.get('/api/cast/shift-confirm/')
            self.assertEqual(first.data['shift']['id'], daytime.pk)
            daytime.delete()
            confirmed = self.cast_client.get('/api/cast/shift-confirm/')
            self.assertEqual(confirmed.data['shift']['start_time_extended'], '24:00')
        scheduled = self.cast_client.get(f'/api/cast/schedule/?date={self.shift_date}')
        self.assertEqual(scheduled.status_code, 200, scheduled.data)
        self.assertEqual(scheduled.data['days'][0]['shifts'][0]['start'], '24:00')
        self.assertEqual(scheduled.data['rooms'][0]['occupied'], [{'start': '24:00', 'end': '29:00'}])
        shift.room = None
        shift.save()
        undecided = self.cast_client.get(f'/api/cast/schedule/?date={self.shift_date}')
        self.assertEqual(undecided.status_code, 200, undecided.data)
        self.assertEqual(undecided.data['days'][0]['shifts'][0]['room_name'], '未定')

    def test_retrospective_clock_in_uses_next_calendar_day(self):
        shift = ShiftAssignment.objects.create(
            store=self.store, cast=self.cast, room=self.room, date=self.shift_date,
            start_time=time(0), start_day_offset=1, end_time=time(5), end_day_offset=1,
        )
        response = self.manager_client.post(f'/api/shifts/{shift.pk}/clock-in/', {}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        shift.refresh_from_db()
        self.assertEqual(shift.clocked_in_at.astimezone(ZoneInfo('Asia/Tokyo')).date(), self.shift_date + timedelta(days=1))
