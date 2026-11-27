"""Manual, audited confirmations independent of cast submission and cash ledgers."""
import uuid
from datetime import date

from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiTypes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Cast, CastAccountingConfirmation, CastAccountingConfirmationEvent, CastDailyCheckout, Store
from .permissions import IsManager
from .store_access import get_user_store
from .services.business_datetime import business_date_for_datetime
from .services.envelope_receipts import digest
from .services.settlement_policy import uses_deferred_settlement


def accounting_state(record):
    return {"collected_amount": record.collected_amount if record else None,
            "unpaid_amount": record.unpaid_amount if record else None,
            "memo": record.memo if record else "", "version": record.version if record else 0,
            "reviewed_at": record.updated_at.isoformat() if record else None,
            "reviewed_by": record.reviewed_by.get_username() if record and record.reviewed_by else None}


def latest_unpaid(cast, day):
    row = CastAccountingConfirmation.objects.filter(store=cast.store, cast=cast, date__lte=day,
        unpaid_amount__isnull=False).order_by("-date").first()
    return {"amount": row.unpaid_amount, "date": row.date.isoformat()} if row else None


@extend_schema_view(get=extend_schema(request=None, responses=OpenApiTypes.OBJECT),
                    post=extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT))
class CastAccountingView(APIView):
    permission_classes = [IsAuthenticated, IsManager]

    def day(self, value):
        try:
            return date.fromisoformat(value)
        except (ValueError, TypeError):
            raise ValidationError("営業日を指定してください。")

    def get(self, request):
        store = get_user_store(request)
        day = self.day(request.query_params.get("date"))
        records = CastAccountingConfirmation.objects.filter(store=store, date=day).select_related("cast", "reviewed_by")
        balances = {}
        for row in CastAccountingConfirmation.objects.filter(store=store, date__lte=day, unpaid_amount__isnull=False).order_by('cast_id', '-date'):
            balances.setdefault(row.cast_id, {"amount": row.unpaid_amount, "date": row.date.isoformat()})
        return Response({"date": day.isoformat(), "deferred": uses_deferred_settlement(store, day),
            "unpaid_balances": balances,
            "rows": [{"cast_id": row.cast_id, **accounting_state(row),
                      "latest_unpaid": balances.get(row.cast_id),
                      "history": [{"before": e.before, "after": e.after,
                                   "recorded_at": e.created_at.isoformat(),
                                   "recorded_by": e.recorded_by.get_username() if e.recorded_by else None}
                                  for e in row.events.select_related("recorded_by").order_by("-pk")[:30]]}
                     for row in records]})

    @transaction.atomic
    def post(self, request):
        store = get_user_store(request)
        Store.objects.select_for_update().get(pk=store.pk)
        data = request.data
        if not isinstance(data, dict) or set(data) - {"date", "cast", "version", "request_id", "collected_amount", "unpaid_amount", "memo"}:
            raise ValidationError("指定できない項目が含まれています。")
        day = self.day(data.get("date"))
        try:
            request_id = uuid.UUID(str(data.get("request_id")))
            cast_id = int(data.get("cast"))
        except (ValueError, TypeError):
            raise ValidationError("対象とリクエストIDを確認してください。")
        cast = Cast.objects.filter(store=store, pk=cast_id).first()
        if not cast:
            return Response({"detail": "対象が見つかりません。"}, status=404)
        signature = digest([store.pk, request.user.pk, dict(data)])
        previous = CastAccountingConfirmationEvent.objects.filter(request_id=request_id).select_related("confirmation").first()
        if previous:
            if previous.request_signature != signature or previous.confirmation.store_id != store.pk:
                return Response({"detail": "同じリクエストIDで別の操作はできません。"}, status=409)
            return Response(accounting_state(previous.confirmation))
        checkout = CastDailyCheckout.objects.filter(store=store, cast=cast, date=day).first()
        if not uses_deferred_settlement(store, day, checkout):
            raise ValidationError("この営業日は従来方式です。既存の受領確認を使用してください。")
        if day > business_date_for_datetime(timezone.now(), store.timezone):
            raise ValidationError("未来の日の確認は記録できません。")
        # A cast submission and daily lock are not prerequisites: accounting may arrive weeks later.
        record = CastAccountingConfirmation.objects.filter(store=store, cast=cast, date=day).first()
        before = accounting_state(record)
        version = data.get("version")
        if isinstance(version, bool) or not isinstance(version, int) or version != before["version"]:
            return Response({"detail": "内容が更新されています。入力を残して最新内容を確認してください。"}, status=409)
        amounts = {}
        for name in ("collected_amount", "unpaid_amount"):
            value = data.get(name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 2147483647):
                raise ValidationError("金額は0以上の整数、未確認の場合は空欄にしてください。")
            amounts[name] = value
        memo = data.get("memo")
        if not isinstance(memo, str) or not memo.strip() or len(memo) > 1000:
            raise ValidationError("確認内容・変更理由を1〜1000文字で入力してください。")
        record = record or CastAccountingConfirmation(store=store, cast=cast, date=day)
        for name, value in amounts.items():
            setattr(record, name, value)
        record.memo = memo.strip()
        record.reviewed_by = request.user
        record.version += 1
        record.save()
        after = accounting_state(record)
        CastAccountingConfirmationEvent.objects.create(confirmation=record, request_id=request_id,
            request_signature=signature, before=before, after=after, recorded_by=request.user)
        return Response(after)
