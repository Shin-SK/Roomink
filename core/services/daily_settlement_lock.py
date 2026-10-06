"""日次精算を確定した後の会計データ変更を一箇所で判定する。"""

from core.models import DailySettlement


def is_daily_settlement_locked(store, business_date):
    return DailySettlement.objects.filter(
        store=store,
        date=business_date,
        status=DailySettlement.Status.LOCKED,
    ).exists()
