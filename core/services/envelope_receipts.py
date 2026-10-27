"""Envelope verification is deliberately disconnected from all cash ledgers."""
import hashlib
import json

from core.models import EnvelopeSubmission
from .sales import get_done_orders_for_business_range
from .reservation_access import card_payment_amount


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def source(checkout):
    orders = list(get_done_orders_for_business_range(checkout.store, checkout.date, checkout.date)
                  .filter(cast_id=checkout.cast_id).order_by("pk"))
    cash = sum(o.total_price if o.payment_method == "CASH" else
               card_payment_amount(o)[1] if o.payment_method == "CARD" else 0 for o in orders)
    signature = digest({
        "orders": [(o.pk, o.total_price, o.payment_method, o.card_include_options,
                    o.course_price, o.options_price, o.extension_price, o.nomination_fee_price,
                    o.updated_at) for o in orders],
        "checkout": [checkout.status == "RETURNED", checkout.submitted_at.timestamp() if checkout.submitted_at else None,
                     checkout.room_cash_taken_amount, checkout.estimated_pay,
                     checkout.daily_expense_total, checkout.cash_returned_to_room_amount,
                     list(checkout.expense_snapshots.order_by("pk").values_list("amount", flat=True))],
        "corrections": list(checkout.cash_corrections.order_by("pk").values_list("pk", flat=True)),
    })
    net = cash - checkout.room_cash_taken_amount
    return {"cash_amount": cash, "taken_amount": checkout.room_cash_taken_amount,
            "deposit_amount": max(0, net), "withdrawal_amount": max(0, -net),
            "source_signature": signature}


def capture(checkout):
    return EnvelopeSubmission.objects.create(checkout=checkout, **source(checkout))


def state(checkout):
    snapshot = checkout.envelope_submissions.first()
    current = source(checkout)
    receipt = getattr(checkout, "envelope_receipt", None)
    revision = digest([snapshot.pk if snapshot else None, current["source_signature"]])
    changed = bool(snapshot and snapshot.source_signature != current["source_signature"])
    received = bool(receipt and receipt.received)
    return {
        "checkout": checkout.pk, "cast_id": checkout.cast_id, "cast_name": checkout.cast.name,
        "date": checkout.date.isoformat(), "snapshot": snapshot.pk if snapshot else None,
        "expected_amount": snapshot.deposit_amount if snapshot else None,
        "withdrawal_amount": snapshot.withdrawal_amount if snapshot else None,
        "submitted_at": snapshot.created_at.isoformat() if snapshot else None,
        "current_amount": current["deposit_amount"], "changed_since_submission": changed,
        "returned": checkout.status == "RETURNED",
        "can_receive": checkout.status != "RETURNED" and (snapshot is None or snapshot.deposit_amount > 0),
        "source_revision": revision, "version": receipt.version if receipt else 0,
        "received": received,
        "needs_reconfirmation": received and receipt.source_revision != revision,
        "actual_amount": receipt.actual_amount if receipt else None,
        "difference_amount": receipt.actual_amount - snapshot.deposit_amount if receipt and receipt.actual_amount is not None and snapshot else None,
        "memo": receipt.memo if receipt else "",
        "reviewed_at": receipt.reviewed_at.isoformat() if receipt and receipt.reviewed_at else None,
        "reviewed_by": (receipt.reviewed_by.get_full_name() or receipt.reviewed_by.username) if receipt and receipt.reviewed_by else None,
        "history": [{"id": e.pk, "before": e.before, "after": e.after,
                     "recorded_by": (e.recorded_by.get_full_name() or e.recorded_by.username) if e.recorded_by else "記録なし",
                     "created_at": e.created_at.isoformat()}
                    for e in receipt.events.select_related("recorded_by").all()[:30]] if receipt else [],
    }
