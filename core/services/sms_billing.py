import math
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db.models import Q, Sum
from django.utils import timezone

from core.models import SmsLog


BASE_MONTHLY_PRICE = 19_800
INCLUDED_SEGMENTS = 200
EXTRA_BLOCK_SIZE = 100
EXTRA_BLOCK_PRICE = 5_000


def _month_bounds(month, timezone_name):
    try:
        local_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        local_timezone = timezone.get_default_timezone()
    start = datetime(month.year, month.month, 1, tzinfo=local_timezone)
    if month.month == 12:
        end = datetime(month.year + 1, 1, 1, tzinfo=local_timezone)
    else:
        end = datetime(month.year, month.month + 1, 1, tzinfo=local_timezone)
    return start, end


def parse_usage_month(value, timezone_name):
    if value:
        try:
            return datetime.strptime(value, "%Y-%m").date().replace(day=1)
        except (TypeError, ValueError):
            raise ValueError("month は YYYY-MM 形式で指定してください。")
    try:
        local_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        local_timezone = timezone.get_default_timezone()
    return timezone.localdate(timezone=local_timezone).replace(day=1)


def sms_usage_summary(store, month=None):
    month = month or parse_usage_month(None, store.timezone)
    start, end = _month_bounds(month, store.timezone)
    billable_attempt = (
        Q(status__in=(SmsLog.Status.SENT, SmsLog.Status.DUMMY))
        | (Q(provider=SmsLog.Provider.TWILIO) & ~Q(provider_message_id=""))
    )
    logs = (
        SmsLog.objects
        .filter(store=store, sent_at__gte=start, sent_at__lt=end, segment_count__gt=0)
        .exclude(template_type=SmsLog.TemplateType.CAST_NOTICE)
        .filter(billable_attempt)
    )
    used_segments = logs.aggregate(total=Sum("segment_count"))["total"] or 0
    extra_segments = max(0, used_segments - INCLUDED_SEGMENTS)
    extra_blocks = math.ceil(extra_segments / EXTRA_BLOCK_SIZE) if extra_segments else 0
    list_price = BASE_MONTHLY_PRICE + extra_blocks * EXTRA_BLOCK_PRICE
    block_limit = INCLUDED_SEGMENTS + extra_blocks * EXTRA_BLOCK_SIZE

    return {
        "month": month.strftime("%Y-%m"),
        "used_segments": used_segments,
        "included_segments": INCLUDED_SEGMENTS,
        "remaining_in_block": max(0, block_limit - used_segments),
        "current_block_limit": block_limit,
        "extra_blocks": extra_blocks,
        "base_monthly_price": BASE_MONTHLY_PRICE,
        "extra_block_size": EXTRA_BLOCK_SIZE,
        "extra_block_price": EXTRA_BLOCK_PRICE,
        "list_price": list_price,
        "billing_exempt": store.sms_billing_exempt,
        "billed_price": 0 if store.sms_billing_exempt else list_price,
    }
