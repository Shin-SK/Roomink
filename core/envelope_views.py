import uuid
from datetime import date

from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiTypes
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import CastDailyCheckout, EnvelopeReceipt, EnvelopeReceiptEvent, Store
from .permissions import IsManager
from .store_access import get_user_store
from .services.envelope_receipts import digest, state
from rest_framework.permissions import IsAuthenticated


@extend_schema_view(
    get=extend_schema(request=None, responses=OpenApiTypes.OBJECT),
    post=extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT),
)
class EnvelopeReceiptsView(APIView):
    permission_classes = [IsAuthenticated, IsManager]

    @transaction.atomic
    def get(self, request):
        store = get_user_store(request)
        Store.objects.select_for_update().get(pk=store.pk)
        try:
            day = date.fromisoformat(request.query_params.get("date", ""))
        except (ValueError, TypeError):
            return Response({"detail": "営業日を指定してください"}, status=400)
        rows = CastDailyCheckout.objects.filter(store=store, date=day).select_related("cast", "store")
        return Response({"date": day.isoformat(), "rows": [state(row) for row in rows]})

    @transaction.atomic
    def post(self, request):
        store = get_user_store(request)
        Store.objects.select_for_update().get(pk=store.pk)
        data = request.data
        try:
            request_id = uuid.UUID(str(data.get("request_id", "")))
            checkout_id = int(data.get("checkout"))
        except (ValueError, TypeError):
            return Response({"detail": "対象とリクエストIDを確認してください"}, status=400)
        checkout = CastDailyCheckout.objects.filter(store=store, pk=checkout_id).select_related("cast", "store").first()
        if not checkout:
            return Response({"detail": "対象が見つかりません"}, status=404)
        signature = digest([request.user.pk, dict(data)])
        previous = EnvelopeReceiptEvent.objects.filter(request_id=request_id).first()
        if previous:
            if previous.receipt.checkout_id != checkout.pk or previous.request_signature != signature:
                return Response({"detail": "同じリクエストIDで別の操作はできません"}, status=409)
            return Response(state(checkout))
        before = state(checkout)
        if data.get("source_revision") != before["source_revision"] or data.get("version") != before["version"]:
            return Response({"detail": "内容が更新されました。入力を残して最新内容を確認してください。"}, status=409)
        action = data.get("action")
        memo = data.get("memo", "")
        if action not in ("receive", "clear") or not isinstance(memo, str) or len(memo) > 1000:
            return Response({"detail": "操作と備考（1000文字以内）を確認してください"}, status=400)
        amount = data.get("actual_amount")
        if action == "receive":
            if not before["can_receive"]:
                return Response({"detail": "提出時の投函記録がある、差戻し中でない封筒だけ確認できます"}, status=400)
            if isinstance(amount, bool) or not isinstance(amount, int) or not 0 <= amount <= 2147483647:
                return Response({"detail": "実際の金額は0以上の整数で入力してください"}, status=400)
            if (before["expected_amount"] is None or amount != before["expected_amount"] or before["changed_since_submission"]) and not memo.strip():
                return Response({"detail": "差額や提出後の訂正がある場合は備考を入力してください"}, status=400)
        elif not before["received"] or not memo.strip():
            return Response({"detail": "受領確認の解除には理由を入力してください"}, status=400)
        receipt, _ = EnvelopeReceipt.objects.get_or_create(checkout=checkout)
        receipt.received = action == "receive"
        if receipt.received:
            receipt.actual_amount = amount
        receipt.memo = memo
        receipt.reviewed_by = request.user
        receipt.reviewed_at = timezone.now()
        receipt.source_revision = before["source_revision"]
        receipt.version += 1
        receipt.save()
        # A reverse one-to-one may have cached its previous missing value.
        checkout = CastDailyCheckout.objects.select_related("cast", "store").get(pk=checkout.pk)
        after = state(checkout)
        for value in (before, after):
            value.pop("history", None)
        EnvelopeReceiptEvent.objects.create(receipt=receipt, request_id=request_id,
                                           request_signature=signature, before=before, after=after,
                                           recorded_by=request.user)
        return Response(state(checkout), status=status.HTTP_200_OK)
