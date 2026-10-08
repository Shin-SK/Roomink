"""Resolve store AND role together, once per request, never by client role claims."""
from dataclasses import dataclass

from rest_framework.exceptions import PermissionDenied

from .models import Store, StoreMembership, UserProfile


@dataclass(frozen=True)
class StoreAccess:
    store: Store
    role: str
    avatar_url: str = ""

    @property
    def store_id(self):
        return self.store.pk


def operator_memberships(user):
    return StoreMembership.objects.filter(user=user, is_active=True, user__is_active=True).select_related("store")


def role_in_store(user, store_id):
    if user is None or not user.is_authenticated or not user.is_active:
        return None
    if user.is_superuser:
        return "manager"
    return operator_memberships(user).filter(store_id=store_id).values_list("role", flat=True).first()


def get_request_profile(request):
    if request is None or not request.user.is_authenticated:
        return None
    if hasattr(request, "_roomink_store_access"):
        return request._roomink_store_access
    user = request.user
    profile = getattr(user, "profile", None)
    # Query selection is for CSV links, whose navigation cannot send a header.
    raw = request.headers.get("X-Roomink-Store")
    query_store = request.GET.get("_store") if request.method in ("GET", "HEAD") else None
    if raw and query_store and raw != query_store:
        raise PermissionDenied("店舗の指定が一致しません。画面を開き直してください。")
    raw = raw or query_store
    if raw:
        if not str(raw).isascii() or not str(raw).isdigit() or len(str(raw)) > 18 or int(raw) < 1:
            raise PermissionDenied("店舗の指定が正しくありません。")
        selected_id = int(raw)
    else:
        selected_id = None
    result = None
    if user.is_superuser:
        selected_id = selected_id or getattr(request, "session", {}).get("platform_store_id") or (profile.store_id if profile else None)
        store = Store.objects.filter(pk=selected_id).first() if selected_id else None
        if store:
            result = StoreAccess(store, "manager", profile.avatar_url if profile else "")
    elif user.is_active and profile:
        if profile.role == UserProfile.Role.CAST:
            if selected_id and selected_id != profile.store_id:
                raise PermissionDenied("この店舗を利用する権限がありません。")
            result = profile if profile.store_id else None
        else:
            memberships = operator_memberships(user)
            if selected_id:
                member = memberships.filter(store_id=selected_id).first()
            else:
                member = memberships.filter(store_id=profile.store_id).first() or memberships.order_by("id").first()
            if member:
                result = StoreAccess(member.store, member.role, profile.avatar_url)
    if selected_id and result is None:
        raise PermissionDenied("この店舗を利用する権限がありません。所属店舗を選び直してください。")
    request._roomink_store_access = result
    return result


def get_user_store(request):
    access = get_request_profile(request)
    if access is None:
        raise PermissionDenied("利用できる店舗がありません。所属店舗を選択してください。")
    return access.store
