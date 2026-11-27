"""Create a new isolated, synthetic demo. Never modify an existing store/account."""
import json
import os
import sys
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import (Store, UserProfile, Cast, Room, Course, Customer, Order,
                         ShiftAssignment, CastDailyCheckout, CastAccountingConfirmation,
                         CastAccountingConfirmationEvent)
from core.services.business_datetime import business_date_for_datetime


class Command(BaseCommand):
    help = 'Create a synthetic settlement demo in staging only; credentials are read from stdin.'

    @transaction.atomic
    def handle(self, *args, **options):
        if os.environ.get('DJANGO_ENV', '').strip().lower() != 'staging' or not settings.SMS_DUMMY_MODE:
            raise CommandError('This command is staging-only and requires dummy SMS.')
        data = json.load(sys.stdin)
        slug = data.get('slug', '')
        if not slug.startswith('settlement-demo-') or Store.objects.filter(slug=slug).exists():
            raise CommandError('A new settlement-demo- slug is required; existing records are never reused.')
        users = {}
        User = get_user_model()
        for role in ('manager', 'cast', 'staff'):
            account = data.get(role, {})
            username, password = account.get('username', ''), account.get('password', '')
            if not username.startswith('settlement-demo-') or len(password) < 16 or User.objects.filter(username=username).exists():
                raise CommandError('New demo-only usernames and strong credentials are required.')
            users[role] = User.objects.create_user(username=username, password=password)
        day = business_date_for_datetime(timezone.now(), 'Asia/Tokyo')
        store = Store.objects.create(name='精算デモ（架空データ・本番に影響しません）', slug=slug,
            timezone='Asia/Tokyo', line_is_enabled=False, deferred_settlement_from=day - timedelta(days=2))
        for role, user in users.items():
            UserProfile.objects.create(user=user, store=store, role=role)
        room = Room.objects.create(store=store, name='デモルーム')
        course = Course.objects.create(store=store, name='デモ60分', duration=60, price=25000)
        customer = Customer.objects.create(store=store, display_name='架空のお客様（送信先なし）')
        casts = [Cast.objects.create(store=store, name=name, course_back_rate=60,
                                    user=users['cast'] if i == 0 else None)
                 for i, name in enumerate(['デモA（現金）', 'デモB（カード）', 'デモC（0円確認）'])]
        for offset in (-2, -1, 0):
            target = day + timedelta(days=offset)
            for i, cast in enumerate(casts):
                ShiftAssignment.objects.create(store=store, cast=cast, room=room, date=target,
                    start_time=time(17), end_time=time(23))
                start = datetime.combine(target, time(17 + i), tzinfo=ZoneInfo('Asia/Tokyo'))
                Order.objects.create(store=store, cast=cast, room=room, customer=customer, course=course,
                    course_name=course.name, course_price=25000, total_price=25000,
                    payment_method='CARD' if i == 1 else 'CASH', card_include_options=True,
                    start=start, end=start + timedelta(hours=1), status='DONE')
        # A deliberately retained old balance demonstrates that it does not change today's estimate.
        CastDailyCheckout.objects.create(store=store, cast=casts[0], date=day - timedelta(days=3),
            estimated_pay=20000, room=room, cast_memo='従来方式の保存例。架空データ。')
        from core.accounting_views import accounting_state
        import uuid
        for cast, collected, unpaid, memo in [
            (casts[0], 10000, 5000, '架空の確認例：本人とLINEで相談。未受取残額5,000円。'),
            (casts[1], None, 15000, '架空の確認例：カード報酬は未受取。回収金額は未確認。'),
            (casts[2], 0, 0, '架空の確認例：回収0円・未受取なしを確認済み。')]:
            record = CastAccountingConfirmation.objects.create(store=store, cast=cast,
                date=day - timedelta(days=1), collected_amount=collected, unpaid_amount=unpaid,
                memo=memo, version=1, reviewed_by=users['manager'])
            CastAccountingConfirmationEvent.objects.create(confirmation=record, request_id=uuid.uuid4(),
                request_signature='synthetic-demo-seed', before=accounting_state(None), after=accounting_state(record),
                recorded_by=users['manager'])
        self.stdout.write(json.dumps({'store_id': store.pk, 'cast_ids': [c.pk for c in casts],
            'dates': [(day + timedelta(days=i)).isoformat() for i in (-3, -2, -1, 0)]}))
