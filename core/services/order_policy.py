from django.utils import timezone

from .business_datetime import business_date_for_datetime


def is_past_business_datetime(start, store, reference_at=None):
    """日時が店舗の現在営業日より前に属するかを返す。"""
    reference_at = reference_at or timezone.now()
    target_business_date = business_date_for_datetime(
        start,
        store.timezone,
    )
    current_business_date = business_date_for_datetime(
        reference_at,
        store.timezone,
    )
    return target_business_date < current_business_date


def is_past_business_day_order(order, reference_at=None):
    """予約が現在の営業日より前に属するかを返す。"""
    return is_past_business_datetime(
        order.start,
        order.store,
        reference_at=reference_at,
    )


def can_modify_business_datetime(user, start, store, reference_at=None):
    """現在・未来日時、またはmanagerによる過去日時の操作を許可する。"""
    if not is_past_business_datetime(start, store, reference_at=reference_at):
        return True
    profile = getattr(user, "profile", None) if user is not None else None
    return profile is not None and profile.role == "manager"


def can_modify_order(user, order, reference_at=None):
    """現在・未来の予約、またはmanagerによる過去予約の変更を許可する。"""
    return can_modify_business_datetime(
        user,
        order.start,
        order.store,
        reference_at=reference_at,
    )
