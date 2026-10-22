"""精算する営業日を明示し、5時を過ぎても本人の未提出分を残す。"""
from datetime import date

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from core.models import CastDailyCheckout, DailySettlement, Order, ShiftAssignment, UserProfile
from core.services.business_datetime import business_date_for_datetime
from core.store_access import get_request_profile


def checkout_context(request):
    cast = getattr(request.user, "cast_profile", None)
    profile = get_request_profile(request)
    if not cast or not profile or profile.role != UserProfile.Role.CAST or profile.store_id != cast.store_id:
        raise PermissionDenied("所属店舗のセラピスト本人だけ利用できます")
    today = business_date_for_datetime(timezone.now(), cast.store.timezone)
    dates = set(ShiftAssignment.objects.filter(cast=cast, store=cast.store, date__lte=today, is_absent=False)
                .values_list("date", flat=True))
    # シフト未登録の接客も、本人の売上がある営業日に限って精算できる。
    dates.update(business_date_for_datetime(start, cast.store.timezone) for start in
                 Order.objects.filter(cast=cast, store=cast.store, status=Order.Status.DONE)
                 .values_list("start", flat=True))
    own_checkouts = CastDailyCheckout.objects.filter(cast=cast, store=cast.store)
    dates.update(own_checkouts.values_list("date", flat=True))
    dates = {day for day in dates if day <= today}
    submitted = set(own_checkouts.exclude(status=CastDailyCheckout.Status.RETURNED).values_list("date", flat=True))
    pending = sorted(dates - submitted, reverse=True)
    locked = set(DailySettlement.objects.filter(store=cast.store, date__lte=today,
                                               status=DailySettlement.Status.LOCKED).values_list("date", flat=True))
    source = request.query_params if request.method == "GET" else request.data
    raw = source.get("date")
    if raw is not None:
        try:
            target = date.fromisoformat(raw)
        except (ValueError, TypeError):
            raise ValidationError("対象営業日をYYYY-MM-DDで指定してください")
        if target > today or (target != today and target not in dates):
            raise PermissionDenied("本人の勤務・売上・精算がある営業日だけ指定できます")
    elif request.method == "GET":
        target = next((day for day in pending if day < today and day not in locked), today)
    else:
        # 旧画面が前日分の見込みを表示したまま、翌日へ誤提出することを防ぐ。
        if any(day < today and day not in locked for day in pending):
            raise ValidationError("精算する営業日を指定してください。画面を再読み込みしてから提出してください")
        target = today
    return cast, target, today, pending, locked
