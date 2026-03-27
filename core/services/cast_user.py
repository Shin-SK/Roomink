"""Cast / Staff / User / UserProfile 一元作成サービス."""
import logging

from django.contrib.auth import get_user_model
from django.db import transaction

from core.models import Cast, UserProfile

User = get_user_model()
logger = logging.getLogger(__name__)


def ensure_user_profile(user, store, role=UserProfile.Role.CAST):
    """User に対して UserProfile が無ければ作成し、あれば返す."""
    profile, created = UserProfile.objects.get_or_create(
        user=user,
        defaults={"store": store, "role": role},
    )
    if not created:
        if profile.store_id != store.id:
            logger.warning(
                "UserProfile store 不整合: user=%s 既存store=%s 要求store=%s",
                user.username, profile.store_id, store.id,
            )
        if profile.role != role:
            logger.warning(
                "UserProfile role 不整合: user=%s 既存role=%s 要求role=%s",
                user.username, profile.role, role,
            )
    return profile


@transaction.atomic
def create_cast_with_user(store, name, avatar_url="", user=None, username=None):
    """Cast を作成し、必要なら User / UserProfile も自動作成する.

    Parameters
    ----------
    store : Store
    name : str
    avatar_url : str
    user : User | None
        既存 User を紐づける場合に指定。
    username : str | None
        User を自動作成する場合のユーザー名。省略時は name をそのまま使う。

    Returns
    -------
    Cast
    """
    if user is None:
        uname = username or name
        user, _ = User.objects.get_or_create(
            username=uname,
            defaults={"is_active": True},
        )

    ensure_user_profile(user, store, role=UserProfile.Role.CAST)

    cast = Cast.objects.create(
        store=store,
        user=user,
        name=name,
        avatar_url=avatar_url,
    )
    return cast


@transaction.atomic
def update_or_create_cast_with_user(store, name, defaults=None):
    """CSV 一括登録などで使う update_or_create 版.

    Cast が既に存在すれば update、なければ User/UserProfile 込みで作成。
    """
    defaults = defaults or {}
    try:
        cast = Cast.objects.get(store=store, name=name)
        for k, v in defaults.items():
            setattr(cast, k, v)
        cast.save()
        return cast, False
    except Cast.DoesNotExist:
        avatar_url = defaults.get("avatar_url", "")
        cast = create_cast_with_user(store=store, name=name, avatar_url=avatar_url)
        return cast, True


# ── Staff ────────────────────────────────────────────


@transaction.atomic
def create_staff_with_user(store, username, password=None, email="",
                           role=UserProfile.Role.STAFF, avatar_url=""):
    """Staff 用の User + UserProfile を一括作成する.

    Returns
    -------
    UserProfile
    """
    user = User.objects.create_user(
        username=username,
        password=password,
        email=email,
    )
    profile = ensure_user_profile(user, store, role=role)
    if avatar_url:
        profile.avatar_url = avatar_url
        profile.save(update_fields=["avatar_url"])
    return profile


@transaction.atomic
def update_or_create_staff_with_user(store, username, defaults=None):
    """CSV 一括登録向け Staff 版.

    既存 UserProfile(staff/manager) があれば update、なければ User 込みで作成。
    """
    defaults = defaults or {}
    try:
        profile = UserProfile.objects.select_related("user").get(
            user__username=username, store=store, role__in=["staff", "manager"],
        )
        for k, v in defaults.items():
            setattr(profile, k, v)
        profile.save()
        return profile, False
    except UserProfile.DoesNotExist:
        role = defaults.pop("role", UserProfile.Role.STAFF)
        avatar_url = defaults.pop("avatar_url", "")
        profile = create_staff_with_user(
            store=store, username=username, role=role, avatar_url=avatar_url,
        )
        return profile, True
