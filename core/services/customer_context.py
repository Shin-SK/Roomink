from rest_framework.exceptions import PermissionDenied, ValidationError

from core.models import Customer


def resolve_customer(request):
    """
    Multi-store 顧客解決。
    request.user に紐づく Customer を ?store=<ID> で特定して返す。

    - 未ログイン        → PermissionDenied (403)
    - Customer 0 件     → PermissionDenied (403)
    - store 指定あり    → 該当 Customer を返す / 無ければ PermissionDenied (403)
    - store 未指定 & 1件 → 自動選択
    - store 未指定 & 複数 → ValidationError (400)
    """
    if not request.user or not request.user.is_authenticated:
        raise PermissionDenied("ログインが必要です")

    qs = Customer.objects.filter(user=request.user).select_related("store")
    customers = list(qs)

    if len(customers) == 0:
        raise PermissionDenied("顧客プロフィールが紐づいていません")

    store_id = request.query_params.get("store") or request.GET.get("store")
    if store_id:
        for c in customers:
            if str(c.store_id) == str(store_id):
                return c
        raise PermissionDenied("指定された店舗に所属していません")

    if len(customers) == 1:
        return customers[0]

    raise ValidationError("複数店舗に所属しています。store パラメータを指定してください")
