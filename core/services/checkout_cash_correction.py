"""Callers hold the store and checkout locks inside an atomic transaction."""
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import APIException, ValidationError


class CheckoutCashConflict(APIException):
    status_code = 409
    default_detail = "精算が更新されています。画面を開き直し、最新の受渡額を確認してください。"
    default_code = "checkout_cash_conflict"


def require_current_checkout(checkout, expected):
    try:
        stamp = parse_datetime(expected) if isinstance(expected, str) else None
    except (TypeError, ValueError):
        stamp = None
    if stamp is None or stamp != checkout.updated_at:
        raise CheckoutCashConflict()


def validate_cash_correction(data):
    from rest_framework import serializers
    if not isinstance(data, dict):
        raise ValidationError("実受渡額を正しい形式で送信してください。")
    raw = data.get("room_cash_taken_amount")
    if isinstance(raw, bool) or raw is None:
        raise ValidationError("実際に渡した金額を0円以上の整数で入力してください。")
    amount = serializers.IntegerField(min_value=0, max_value=2147483647).run_validation(raw)
    reason = data.get("reason")
    if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 500:
        raise ValidationError("訂正理由を1〜500文字で入力してください。")
    return amount, reason.strip()


def correct_cash_receipt(checkout, amount, reason, actor, *, order=None):
    from core.models import CastCheckoutCashCorrection
    fields = ("room_cash_taken_amount", "actual_take_home_amount", "office_cash_paid_amount", "cash_returned_to_room_amount", "room_id")
    before = {field: getattr(checkout, field) for field in fields}
    if checkout.room_cash_taken_amount == amount and checkout.actual_take_home_amount == amount:
        return
    checkout.room_cash_taken_amount = amount
    checkout.actual_take_home_amount = amount
    checkout._cash_recorded_by_id = actor.pk
    checkout.save(update_fields=["room_cash_taken_amount", "actual_take_home_amount", "updated_at"])
    CastCheckoutCashCorrection.objects.create(
        checkout=checkout, order=order, reason=reason, before=before,
        after={field: getattr(checkout, field) for field in fields}, corrected_by=actor,
    )
