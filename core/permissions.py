import logging

from django.utils import timezone
from rest_framework.permissions import BasePermission, SAFE_METHODS

from .services.order_policy import can_modify_order, is_past_business_day_order
from .models import UserProfile


logger = logging.getLogger(__name__)


class IsManagerOrStaff(BasePermission):
    """運営権限（manager / staff）だけに操作を許可する。"""

    message = "この操作を行えるのはマネージャーまたはスタッフのみです。"

    def has_permission(self, request, view):
        profile = getattr(request.user, "profile", None)
        return profile is not None and profile.role in (
            UserProfile.Role.MANAGER,
            UserProfile.Role.STAFF,
        )


class IsManager(BasePermission):
    """マネージャーだけに操作を許可する。"""

    message = "この操作を行えるのはマネージャーのみです。"

    def has_permission(self, request, view):
        profile = getattr(request.user, "profile", None)
        return profile is not None and profile.role == UserProfile.Role.MANAGER


class IsManagerOrStaffReadOnlyManagerWrite(BasePermission):
    """マスター参照は運営に許可し、変更はマネージャーだけに許可する。"""

    message = "このマスターを変更できるのはマネージャーのみです。"

    def has_permission(self, request, view):
        profile = getattr(request.user, "profile", None)
        if profile is None:
            return False
        if profile.role == UserProfile.Role.MANAGER:
            return True
        return profile.role == UserProfile.Role.STAFF and request.method in SAFE_METHODS


class IsOperatorOrCastReadOnlyManagerWrite(BasePermission):
    """ルーム参照はキャストにも許可し、変更はマネージャーだけに許可する。"""

    message = "ルームを変更できるのはマネージャーのみです。"

    def has_permission(self, request, view):
        profile = getattr(request.user, "profile", None)
        if profile is None:
            return False
        if profile.role == UserProfile.Role.MANAGER:
            return True
        return (
            profile.role in (UserProfile.Role.STAFF, UserProfile.Role.CAST)
            and request.method in SAFE_METHODS
        )


class PastOrderManagerOnlyPermission(BasePermission):
    """過去営業日の予約変更をmanagerだけに許可する。"""

    message = "過去営業日の予約を変更できるのはマネージャーのみです。"

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True

        reference_at = timezone.now()
        if not can_modify_order(request.user, obj, reference_at=reference_at):
            return False

        if is_past_business_day_order(obj, reference_at=reference_at):
            logger.info(
                "Past order mutation allowed: order_id=%s user_id=%s action=%s",
                obj.pk,
                request.user.pk,
                getattr(view, "action", request.method.lower()),
            )
        return True
