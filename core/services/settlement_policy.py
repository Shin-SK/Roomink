"""A dated, per-store transition; historical submissions keep their original mode."""


def uses_deferred_settlement(store, day, checkout=None):
    if checkout is not None:
        return not checkout.cash_handover_recorded
    return bool(store.deferred_settlement_from and day >= store.deferred_settlement_from)


def require_legacy_handover(checkout):
    from rest_framework.exceptions import ValidationError
    if not checkout.cash_handover_recorded:
        raise ValidationError("後日経理確認方式です。受渡・繰越の自動記録は行わず、日給一覧の経理確認で記録してください。")
