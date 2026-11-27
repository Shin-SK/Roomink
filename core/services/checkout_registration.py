"""Store registration uses the existing checkout ledger, never an inferred payment."""
import uuid
from datetime import date

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException, ValidationError

from core.models import (CastDailyCheckout, CastCheckoutExpenseSnapshot, CastCheckoutRegistration,
                         CastExpenseTemplate, Order, ShiftAssignment, Store)
from .business_datetime import business_date_for_datetime, business_day_range
from .envelope_receipts import capture, digest


class RegistrationConflict(APIException):
    status_code = 409
    default_detail = '精算内容が更新されています。画面を開き直して確認してください。'


def unrecorded_prior_dates(cast, before):
    days = set(ShiftAssignment.objects.filter(store=cast.store, cast=cast, date__lt=before, is_absent=False)
               .values_list('date', flat=True))
    start, _ = business_day_range(before, cast.store.timezone)
    days.update(business_date_for_datetime(stamp, cast.store.timezone)
                for stamp in Order.objects.filter(store=cast.store, cast=cast, status='DONE', start__lt=start)
                .values_list('start', flat=True))
    checkouts = CastDailyCheckout.objects.filter(store=cast.store, cast=cast, date__lt=before)
    days.update(checkouts.filter(status='RETURNED').values_list('date', flat=True))
    days.difference_update(checkouts.exclude(status='RETURNED').values_list('date', flat=True))
    return sorted(days)


def settlement_state(cast, day):
    from core.views import (_cast_carryover_before, _checkout_compensation, _compute_cast_done_sales,
                            _cast_expense_totals, _compute_payment_summary, _suggest_checkout_room)
    checkout = CastDailyCheckout.objects.filter(cast=cast, store=cast.store, date=day).prefetch_related('expense_snapshots').first()
    from .settlement_policy import uses_deferred_settlement
    if uses_deferred_settlement(cast.store, day, checkout):
        from core.accounting_views import latest_unpaid
        return {'settlement_mode': 'DEFERRED', 'can_register_by_store': False,
                'cash_handover_recorded': False, 'checkout_id': checkout.pk if checkout else None,
                'confirmed_unpaid': latest_unpaid(cast, day)}
    recorded = bool(checkout and checkout.status != 'RETURNED')
    sales = _compute_cast_done_sales(cast, day)
    expenses = _cast_expense_totals(cast, day, sales['done_count'])
    fee = _compute_payment_summary(cast.store, cast, day)
    opening = _cast_carryover_before(cast, day)
    compensation = _checkout_compensation(checkout) if recorded else sales['estimated_pay'] - expenses['expense_total']
    room = checkout.room if checkout and checkout.room_id else _suggest_checkout_room(cast, day)
    pending = [d.isoformat() for d in unrecorded_prior_dates(cast, day)]
    # Revision protects against order/expense/rate/room/earlier-payment changes while the form is open.
    revision = digest({'sales': sales, 'expenses': expenses, 'fee': fee, 'opening': opening,
                       'room': room.pk if room else None, 'pending_dates': pending,
                       'templates': list(CastExpenseTemplate.objects.filter(cast=cast, is_active=True).order_by('pk').values_list('pk', 'name', 'amount', 'memo')),
                       'checkout': [checkout.pk, checkout.updated_at] if checkout else None})
    taken = checkout.room_cash_taken_amount if recorded else None
    office = checkout.office_cash_paid_amount if checkout else 0
    return {
        'carryover_opening_amount': opening, 'settlement_compensation_amount': compensation,
        'receivable_amount': opening + compensation,
        'room_cash_taken_amount': taken, 'office_cash_paid_amount': office,
        'remaining_receivable_amount': opening + compensation - (taken or 0) - office,
        'cash_handover_recorded': recorded,
        'unrecorded_prior_dates': pending,
        'registration_source': checkout.registration_source if recorded else None,
        'checkout_id': checkout.pk if checkout else None,
        'settlement_source_revision': revision,
    }


@transaction.atomic
def register_by_store(store, actor, data):
    from core.models import Cast
    from core.views import (_compute_cast_done_sales, _compute_payment_summary, _cast_expense_totals,
                            _require_daily_settlement_open, _suggest_checkout_room)
    from .compensation import CURRENT_PAY_VERSION
    from django.shortcuts import get_object_or_404
    Store.objects.select_for_update().get(pk=store.pk)
    try:
        day = date.fromisoformat(data.get('date', ''))
        request_id = uuid.UUID(str(data.get('request_id', '')))
    except (ValueError, TypeError):
        raise ValidationError('営業日とリクエストIDを確認してください。')
    cast_id = serializers.IntegerField(min_value=1).run_validation(data.get('cast'))
    cast = get_object_or_404(Cast.objects.select_related('store'), store=store, pk=cast_id)
    from .settlement_policy import uses_deferred_settlement
    existing_mode = CastDailyCheckout.objects.filter(store=store, cast=cast, date=day).first()
    if uses_deferred_settlement(store, day, existing_mode):
        raise ValidationError('後日経理確認方式では当日の受取金額登録は不要です。経理確認で記録してください。')
    signature = digest([actor.pk, store.pk, dict(data)])
    previous = CastCheckoutRegistration.objects.filter(request_id=request_id).select_related('checkout').first()
    if previous:
        if previous.checkout.store_id != store.pk or previous.request_signature != signature:
            raise RegistrationConflict()
        return previous.checkout, False
    today = business_date_for_datetime(timezone.now(), store.timezone)
    if day > today:
        raise ValidationError('未来の日の精算は登録できません。')
    _require_daily_settlement_open(store, day)
    start, end = business_day_range(day, store.timezone)
    if not (ShiftAssignment.objects.filter(store=store, cast=cast, date=day, is_absent=False).exists()
            or Order.objects.filter(store=store, cast=cast, status='DONE', start__gte=start, start__lt=end).exists()
            or CastDailyCheckout.objects.filter(store=store, cast=cast, date=day).exists()):
        raise ValidationError('勤務・売上・精算のある営業日を指定してください。')
    raw = data.get('room_cash_taken_amount')
    if isinstance(raw, bool) or raw is None or raw == '':
        raise ValidationError('実際に受け取った金額を入力してください。0円の場合も入力が必要です。')
    amount = serializers.IntegerField(min_value=0, max_value=2147483647).run_validation(raw)
    reason = data.get('reason')
    if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 500:
        raise ValidationError('確認内容を1〜500文字で入力してください。')
    state = settlement_state(cast, day)
    if not data.get('source_revision') or data['source_revision'] != state['settlement_source_revision'] or state['cash_handover_recorded']:
        raise RegistrationConflict()
    if amount > max(0, state['receivable_amount'] - state['office_cash_paid_amount']):
        raise ValidationError('受取可能額を超える金額は登録できません。既存の受渡記録を確認してください。')
    existing = CastDailyCheckout.objects.select_for_update().filter(store=store, cast=cast, date=day).first()
    instance = existing or CastDailyCheckout(store=store, cast=cast, date=day)
    before = {'room_cash_taken_amount': existing.room_cash_taken_amount,
              'registration_source': existing.registration_source} if existing else None
    if existing:
        instance.expense_snapshots.all().delete()
    sales = _compute_cast_done_sales(cast, day)
    fee = _compute_payment_summary(store, cast, day)
    expenses = _cast_expense_totals(cast, day, sales['done_count'])
    for name in ('done_count', 'total_sales', 'estimated_pay', 'course_sales', 'options_sales'):
        setattr(instance, name, sales[name])
    for name in ('customer_payment_surcharge', 'customer_payment_total', 'payment_fee_estimate', 'net_sales_after_payment_fee'):
        setattr(instance, name, fee[name])
    instance.daily_expense_total = expenses['daily_expense_total']
    instance.pay_calculation_version = CURRENT_PAY_VERSION
    if not instance.room_id:
        instance.room = _suggest_checkout_room(cast, day)
    instance.room_cash_taken_amount = instance.actual_take_home_amount = amount
    instance.registration_source = 'STORE'
    instance.registered_by = actor
    instance.status = 'SUBMITTED'
    instance.submitted_at = timezone.now()
    instance.reviewed_at = instance.reviewed_by = None
    instance.manager_memo = reason.strip()
    # No cast checklist is claimed on their behalf. Existing cash returns/office payments stay intact.
    instance.checklist_json = {}
    instance._cash_recorded_by_id = actor.pk
    instance.save()
    CastCheckoutExpenseSnapshot.objects.bulk_create([
        CastCheckoutExpenseSnapshot(checkout=instance, template=t, name=t.name,
                                    amount=t.amount if sales['done_count'] else 0, memo=t.memo)
        for t in CastExpenseTemplate.objects.filter(cast=cast, is_active=True)
    ])
    capture(instance)
    CastCheckoutRegistration.objects.create(checkout=instance, request_id=request_id,
        request_signature=signature, reason=reason.strip(), recorded_by=actor,
        snapshot={'date': day.isoformat(), 'room_cash_taken_amount': amount,
                  'before': before,
                  'compensation_amount': state['settlement_compensation_amount'],
                  'carryover_opening_amount': state['carryover_opening_amount']})
    return instance, True
