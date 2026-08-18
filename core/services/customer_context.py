from rest_framework.exceptions import PermissionDenied, ValidationError

from core.models import Customer


def resolve_customer(request):
    """
    Multi-store 顧客解決（ログイン済み前提）。
    request.user に紐づく Customer を ?store_slug=<slug> または旧 ?store=<ID> で特定して返す。
    未ログインの判定は DRF の IsAuthenticated に任せる。

    - Customer 0 件     → PermissionDenied (403)
    - store 指定あり    → 該当 Customer を返す / 無ければ PermissionDenied (403)
    - store 未指定 & 1件 → 自動選択
    - store 未指定 & 複数 → ValidationError (400)
    """
    qs = Customer.objects.filter(user=request.user).select_related("store").prefetch_related("store__slug_aliases")
    customers = list(qs)

    if len(customers) == 0:
        raise PermissionDenied("顧客プロフィールが紐づいていません")

    store_slug = (request.query_params.get("store_slug") or request.GET.get("store_slug") or "").strip().lower()
    if store_slug:
        for c in customers:
            if c.store.slug == store_slug:
                return c
            if c.store.slug_aliases.filter(slug=store_slug).exists():
                return c
        raise PermissionDenied("指定された店舗に所属していません")

    store_id = request.query_params.get("store") or request.GET.get("store")
    if store_id:
        for c in customers:
            if str(c.store_id) == str(store_id):
                return c
        raise PermissionDenied("指定された店舗に所属していません")

    if len(customers) == 1:
        return customers[0]

    raise ValidationError("複数店舗に所属しています。store パラメータを指定してください")
