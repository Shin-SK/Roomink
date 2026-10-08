"""Store-scoped membership and recipient-bound invitation APIs."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.middleware.csrf import get_token
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from .models import Store, StoreInvitation, StoreMembership, StoreMembershipEvent
from .permissions import IsManager
from .store_access import get_user_store, role_in_store


def audit_membership(store, user, actor, action, role=""):
    StoreMembershipEvent.objects.create(store=store, user=user, actor=actor, action=action, role=role)


def require_manager(user, store):
    # Recheck inside the store transaction, including after concurrent revocation.
    if role_in_store(user, store.pk) != "manager":
        raise PermissionDenied("この店舗の管理権限がありません。")


def serialize_invitation(invitation, *, recipient=False):
    result = {
        "id": str(invitation.pk), "store_id": invitation.store_id,
        "store_name": invitation.store.name, "role": invitation.role,
        "status": invitation.status, "expires_at": invitation.expires_at,
        "expired": invitation.expires_at <= timezone.now(),
    }
    if recipient:
        result["invited_by_name"] = invitation.invited_by.username if invitation.invited_by else ""
    else:
        result["username"] = invitation.recipient.username
    return result


class InviteInput(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    role = serializers.ChoiceField(choices=["staff", "manager"], default="staff")


class InvitationThrottle(UserRateThrottle):
    scope = "store_invitation"
    rate = "30/hour"


class StoreInvitationView(APIView):
    permission_classes = [IsAuthenticated, IsManager]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        store = get_user_store(request)
        invitations = StoreInvitation.objects.filter(
            store=store, status=StoreInvitation.Status.PENDING, expires_at__gt=timezone.now(),
        ).select_related("store", "recipient").order_by("-created_at")[:100]
        return Response({"results": [serialize_invitation(item) for item in invitations]})

    @extend_schema(request=InviteInput, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        throttle = InvitationThrottle()
        if not throttle.allow_request(request, self):
            self.throttled(request, throttle.wait())
        serializer = InviteInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            store = Store.objects.select_for_update().get(pk=get_user_store(request).pk)
            require_manager(request.user, store)
            recipient = get_user_model().objects.filter(
                username=serializer.validated_data["username"], is_active=True,
                is_superuser=False, profile__role__in=["staff", "manager"],
            ).first()
            # Only existing operator accounts can receive invitations. Never
            # return another store's memberships or contact details.
            if recipient and not StoreMembership.objects.filter(user=recipient, store=store, is_active=True).exists():
                StoreInvitation.objects.filter(
                    store=store, recipient=recipient, status="pending",
                    expires_at__lte=timezone.now(),
                ).update(status="revoked", responded_at=timezone.now())
                invitation, created = StoreInvitation.objects.get_or_create(
                    store=store, recipient=recipient, status="pending",
                    defaults={"invited_by": request.user, "role": serializer.validated_data["role"], "expires_at": timezone.now() + timedelta(days=7)},
                )
                if created:
                    audit_membership(store, recipient, request.user, "invited", invitation.role)
        return Response({"detail": "招待を受け付けました。対象が既存のスタッフアカウントで未所属の場合、本人の「所属店舗・招待」に届きます。"}, status=status.HTTP_202_ACCEPTED)


class StoreInvitationRevokeView(APIView):
    permission_classes = [IsAuthenticated, IsManager]

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request, invitation_id):
        with transaction.atomic():
            store = Store.objects.select_for_update().get(pk=get_user_store(request).pk)
            require_manager(request.user, store)
            invitation = get_object_or_404(StoreInvitation, pk=invitation_id, store=store)
            if invitation.status == "pending":
                invitation.status = "revoked"
                invitation.responded_at = timezone.now()
                invitation.save(update_fields=["status", "responded_at"])
                audit_membership(store, invitation.recipient, request.user, "invite_revoked", invitation.role)
        return Response({"ok": True})


class MyStoreAccessView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        # Deliberately independent of a selected store, including after removal.
        members = StoreMembership.objects.filter(user=request.user, is_active=True).select_related("store").order_by("store__name", "id")
        invites = StoreInvitation.objects.filter(
            recipient=request.user, status="pending", expires_at__gt=timezone.now(),
        ).select_related("store", "invited_by").order_by("-created_at")
        return Response({
            "csrf_token": get_token(request),
            "memberships": [{"store_id": m.store_id, "store_name": m.store.name, "role": m.role} for m in members],
            "invitations": [serialize_invitation(i, recipient=True) for i in invites],
        })


class InvitationResponseInput(serializers.Serializer):
    action = serializers.ChoiceField(choices=["accept", "decline"])


class MyStoreInvitationRespondView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=InvitationResponseInput, responses=OpenApiTypes.OBJECT)
    def post(self, request, invitation_id):
        serializer = InvitationResponseInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = get_object_or_404(StoreInvitation, pk=invitation_id, recipient=request.user)
        action = serializer.validated_data["action"]
        with transaction.atomic():
            store = Store.objects.select_for_update().get(pk=invitation.store_id)
            invitation.refresh_from_db()
            desired = "accepted" if action == "accept" else "declined"
            if invitation.status == desired:
                return Response({"ok": True, "status": desired})
            if invitation.status != "pending" or invitation.expires_at <= timezone.now():
                raise ValidationError("この招待は有効ではありません。管理者に再招待を依頼してください。")
            if action == "accept":
                require_manager(invitation.invited_by, store)
                get_user_model().objects.select_for_update().get(pk=request.user.pk)
                profile = getattr(request.user, "profile", None)
                if not profile or profile.role not in ("manager", "staff"):
                    raise PermissionDenied("スタッフアカウントで承認してください。")
                # Do not change an existing membership's role through an old invite.
                member, created = StoreMembership.objects.get_or_create(
                    user=request.user, store=store,
                    defaults={"role": invitation.role},
                )
                if not created and not member.is_active:
                    member.is_active = True
                    member.role = invitation.role
                    member.save(update_fields=["is_active", "role", "updated_at"])
            invitation.status = desired
            invitation.responded_at = timezone.now()
            invitation.save(update_fields=["status", "responded_at"])
            audit_membership(store, request.user, request.user, "invite_" + desired, invitation.role)
        return Response({"ok": True, "status": desired})
