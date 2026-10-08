"""Private, contract-scoped multi-store management APIs.

These endpoints never accept an operation-group identifier from the client.
The selected store determines the group, and only an explicit group manager can
see or change data within that single group.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .membership_views import InvitationThrottle, audit_membership
from .models import (
    OperationGroup,
    OperationGroupEvent,
    OperationGroupMembership,
    Store,
    StoreInvitation,
    StoreMembership,
    UserProfile,
)
from .serializers import StaffCreateSerializer
from .store_access import get_user_store, is_operation_group_manager


class StoreIdsInput(serializers.Serializer):
    store_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        min_length=1,
        max_length=30,
    )

    def validate_store_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("所属店舗が重複しています。")
        return value


class GroupStaffCreateInput(StaffCreateSerializer, StoreIdsInput):
    is_operation_group_manager = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs.get("is_operation_group_manager") and attrs.get("role") != "manager":
            raise serializers.ValidationError(
                {"is_operation_group_manager": "運営管理者は少なくとも1店舗のマネージャーにしてください。"}
            )
        return attrs


class GroupInviteInput(StoreIdsInput):
    username = serializers.CharField(max_length=150)
    role = serializers.ChoiceField(choices=["staff", "manager"], default="staff")


class GroupManagerInput(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    is_active = serializers.BooleanField()


def operation_group_for_request(request):
    store = get_user_store(request)
    if not store.operation_group_id or not is_operation_group_manager(
        request.user, store.operation_group_id
    ):
        raise PermissionDenied("この運営管理設定を利用する権限がありません。")
    return store.operation_group_id


def scoped_stores(group_id, requested_ids, *, lock=False):
    queryset = Store.objects.filter(operation_group_id=group_id)
    if lock:
        queryset = queryset.select_for_update()
    stores = list(queryset.filter(pk__in=requested_ids).order_by("name", "id"))
    if len(stores) != len(requested_ids):
        raise ValidationError("この運営グループに所属しない店舗は選択できません。")
    return stores


def group_snapshot(group_id):
    stores = list(
        Store.objects.filter(operation_group_id=group_id).order_by("name", "id")
    )
    manager_user_ids = set(
        OperationGroupMembership.objects.filter(
            operation_group_id=group_id,
            role=OperationGroupMembership.Role.MANAGER,
            is_active=True,
        ).values_list("user_id", flat=True)
    )
    memberships = (
        StoreMembership.objects.filter(store__operation_group_id=group_id, is_active=True)
        .select_related("user")
        .order_by("user__username", "store__name", "id")
    )
    people = {}
    for membership in memberships:
        person = people.setdefault(
            membership.user_id,
            {
                "username": membership.user.username,
                "is_operation_group_manager": membership.user_id in manager_user_ids,
                "memberships": [],
            },
        )
        person["memberships"].append(
            {
                "store_id": membership.store_id,
                "role": membership.role,
            }
        )
    return {
        "stores": [{"id": store.pk, "name": store.name} for store in stores],
        "people": list(people.values()),
    }


def audit_group(group_id, *, action, actor, user=None, store=None):
    OperationGroupEvent.objects.create(
        operation_group_id=group_id,
        actor=actor,
        user=user,
        store=store,
        action=action,
    )


class OperationGroupSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(group_snapshot(operation_group_for_request(request)))


class OperationGroupStaffCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=GroupStaffCreateInput, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = GroupStaffCreateInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            group_id = operation_group_for_request(request)
            stores = scoped_stores(
                group_id,
                serializer.validated_data["store_ids"],
                lock=True,
            )
            profile = serializer.save(store=stores[0])
            role = serializer.validated_data["role"]
            for store in stores:
                membership, _ = StoreMembership.objects.get_or_create(
                    user=profile.user,
                    store=store,
                    defaults={"role": role, "is_active": True},
                )
                # The first membership may be created by the legacy profile
                # provisioning signal. This is a new user either way, so
                # record every selected store consistently.
                audit_membership(store, profile.user, request.user, "created", membership.role)
                audit_group(
                    group_id,
                    action="staff_created",
                    actor=request.user,
                    user=profile.user,
                    store=store,
                )
            if serializer.validated_data["is_operation_group_manager"]:
                OperationGroupMembership.objects.create(
                    operation_group_id=group_id,
                    user=profile.user,
                )
                audit_group(
                    group_id,
                    action="manager_granted",
                    actor=request.user,
                    user=profile.user,
                )
        return Response(group_snapshot(group_id), status=status.HTTP_201_CREATED)


class OperationGroupInvitationView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=GroupInviteInput, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        throttle = InvitationThrottle()
        if not throttle.allow_request(request, self):
            self.throttled(request, throttle.wait())
        serializer = GroupInviteInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            group_id = operation_group_for_request(request)
            stores = scoped_stores(
                group_id,
                serializer.validated_data["store_ids"],
                lock=True,
            )
            recipient = get_user_model().objects.filter(
                username=serializer.validated_data["username"],
                is_active=True,
                is_superuser=False,
                profile__role__in=[UserProfile.Role.STAFF, UserProfile.Role.MANAGER],
            ).first()
            if recipient:
                for store in stores:
                    if StoreMembership.objects.filter(
                        user=recipient,
                        store=store,
                        is_active=True,
                    ).exists():
                        continue
                    StoreInvitation.objects.filter(
                        store=store,
                        recipient=recipient,
                        status=StoreInvitation.Status.PENDING,
                        expires_at__lte=timezone.now(),
                    ).update(
                        status=StoreInvitation.Status.REVOKED,
                        responded_at=timezone.now(),
                    )
                    invitation, created = StoreInvitation.objects.get_or_create(
                        store=store,
                        recipient=recipient,
                        status=StoreInvitation.Status.PENDING,
                        defaults={
                            "invited_by": request.user,
                            "role": serializer.validated_data["role"],
                            "expires_at": timezone.now() + timedelta(days=7),
                        },
                    )
                    if created:
                        audit_membership(
                            store,
                            recipient,
                            request.user,
                            "invited",
                            invitation.role,
                        )
                        audit_group(
                            group_id,
                            action="staff_invited",
                            actor=request.user,
                            user=recipient,
                            store=store,
                        )
        return Response(
            {
                "detail": "対象が既存のスタッフアカウントで未所属の場合、本人の「所属店舗・招待」に届きます。"
            },
            status=status.HTTP_202_ACCEPTED,
        )


class OperationGroupManagerView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=GroupManagerInput, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = GroupManagerInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            group_id = operation_group_for_request(request)
            # Serialise manager removals so two requests cannot both remove
            # what they each observed as a non-final manager.
            OperationGroup.objects.select_for_update().get(pk=group_id)
            user = get_user_model().objects.select_for_update().filter(
                username=serializer.validated_data["username"],
                is_active=True,
                is_superuser=False,
            ).first()
            if not user:
                raise ValidationError("この運営グループで管理できるスタッフが見つかりません。")
            is_store_manager = StoreMembership.objects.filter(
                user=user,
                store__operation_group_id=group_id,
                role=UserProfile.Role.MANAGER,
                is_active=True,
            ).exists()
            if not is_store_manager:
                raise ValidationError("運営管理者にするには、グループ内の店舗マネージャーである必要があります。")
            membership, _ = OperationGroupMembership.objects.select_for_update().get_or_create(
                operation_group_id=group_id,
                user=user,
                defaults={"is_active": False},
            )
            desired_active = serializer.validated_data["is_active"]
            if membership.is_active == desired_active:
                return Response(group_snapshot(group_id))
            if not desired_active and not OperationGroupMembership.objects.filter(
                operation_group_id=group_id,
                is_active=True,
            ).exclude(pk=membership.pk).exists():
                raise ValidationError("最後の有効な運営管理者は解除できません。")
            membership.is_active = desired_active
            membership.save(update_fields=["is_active", "updated_at"])
            audit_group(
                group_id,
                action="manager_granted" if desired_active else "manager_revoked",
                actor=request.user,
                user=user,
            )
        return Response(group_snapshot(group_id))
