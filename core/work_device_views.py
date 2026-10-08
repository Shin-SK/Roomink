"""Roomink Work Phase 2 device identity and store-subscription foundation."""

import hashlib
import secrets
import string
import uuid
from datetime import timedelta

from django.contrib.auth import authenticate
from django.db import transaction
from django.utils import timezone
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from .models import (
    CallLog,
    Store,
    WorkDevice,
    WorkDeviceCredential,
    WorkDeviceEvent,
    WorkDeviceLinkRequest,
    WorkDeviceStore,
)
from .operation_group_views import operation_group_for_request, scoped_stores
from .store_access import is_operation_group_manager, operator_memberships


TOKEN_TTL = timedelta(days=90)
LINK_TTL = timedelta(minutes=10)
LINK_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def _hash_secret(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _new_link_code():
    return "".join(secrets.choice(LINK_ALPHABET) for _ in range(8))


def _issue_credential(device):
    token = secrets.token_urlsafe(48)
    WorkDeviceCredential.objects.create(
        device=device,
        token_hash=_hash_secret(token),
        token_prefix=token[:10],
        expires_at=timezone.now() + TOKEN_TTL,
    )
    return token


def _replace_subscriptions(device, stores):
    desired_ids = {store.pk for store in stores}
    device.store_subscriptions.exclude(store_id__in=desired_ids).delete()
    for store in stores:
        WorkDeviceStore.objects.update_or_create(
            device=device,
            store=store,
            defaults={"is_receiving": True},
        )


def _subscription_is_entitled(device, subscription):
    if device.kind == WorkDevice.Kind.PERSONAL:
        return bool(
            device.owner_id
            and device.owner.is_active
            and operator_memberships(device.owner).filter(
                store_id=subscription.store_id,
                role__in=("manager", "staff"),
            ).exists()
        )
    return bool(
        device.approved_by_id
        and subscription.store.operation_group_id
        and is_operation_group_manager(
            device.approved_by,
            subscription.store.operation_group_id,
        )
    )


def entitled_subscriptions(device, *, receiving_only=False):
    subscriptions = device.store_subscriptions.select_related(
        "store", "store__operation_group", "device__owner", "device__approved_by"
    )
    if receiving_only:
        subscriptions = subscriptions.filter(is_receiving=True)
    return [sub for sub in subscriptions if _subscription_is_entitled(device, sub)]


def _device_payload(device, *, operation_group_id=None):
    subscriptions = list(
        device.store_subscriptions.select_related("store").order_by("store__name", "store_id")
    )
    if operation_group_id is not None:
        subscriptions = [
            sub for sub in subscriptions
            if sub.store.operation_group_id == operation_group_id
        ]
    return {
        "id": str(device.pk),
        "device_key": str(device.device_key),
        "label": device.label,
        "kind": device.kind,
        "kind_label": device.get_kind_display(),
        "platform": device.platform,
        "platform_label": device.get_platform_display(),
        "status": device.status,
        "status_label": device.get_status_display(),
        "owner": device.owner.username if device.owner_id else None,
        "approved_by": device.approved_by.username if device.approved_by_id else None,
        "last_seen_at": device.last_seen_at,
        "created_at": device.created_at,
        "stores": [
            {
                "id": sub.store_id,
                "name": sub.store.name,
                "is_receiving": sub.is_receiving,
                "is_entitled": _subscription_is_entitled(device, sub),
            }
            for sub in subscriptions
        ],
    }


class PublicWorkThrottle(SimpleRateThrottle):
    scope = "roomink_work_public"
    rate = "20/hour"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class WorkLoginThrottle(PublicWorkThrottle):
    scope = "roomink_work_login"
    rate = "10/minute"


class WorkDeviceAuthentication(BaseAuthentication):
    keyword = "RoominkWork"

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header:
            return None
        try:
            scheme, token = header.split(" ", 1)
        except ValueError as exc:
            raise AuthenticationFailed("端末認証が正しくありません。") from exc
        if scheme != self.keyword or not token:
            return None
        credential = (
            WorkDeviceCredential.objects.select_related(
                "device", "device__owner", "device__approved_by"
            )
            .filter(token_hash=_hash_secret(token), revoked_at__isnull=True)
            .first()
        )
        now = timezone.now()
        if not credential or credential.expires_at <= now:
            raise AuthenticationFailed("端末認証の有効期限が切れています。")
        device = credential.device
        if device.status == WorkDevice.Status.REVOKED:
            raise AuthenticationFailed("この端末は失効しています。")
        if device.owner_id and not device.owner.is_active:
            raise AuthenticationFailed("この端末の利用者は無効です。")
        if not credential.last_used_at or credential.last_used_at < now - timedelta(minutes=5):
            credential.last_used_at = now
            credential.save(update_fields=["last_used_at"])
        request.work_device = device
        user = device.owner or device.approved_by
        if not user or not user.is_active:
            raise AuthenticationFailed("この端末の承認者を確認できません。")
        return user, credential


class WorkDeviceAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "core.work_device_views.WorkDeviceAuthentication"
    name = "RoominkWorkAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "header",
            "name": "Authorization",
            "description": "Roomink Work端末トークン: `RoominkWork <token>`",
        }


class IsWorkDevice(BasePermission):
    def has_permission(self, request, view):
        return bool(getattr(request, "work_device", None))


class PersonalLoginInput(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(trim_whitespace=False)
    device_key = serializers.UUIDField()
    label = serializers.CharField(max_length=80)
    platform = serializers.ChoiceField(choices=WorkDevice.Platform.choices)
    store_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), min_length=1, max_length=30
    )

    def validate_store_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("店舗が重複しています。")
        return value


class SharedLinkInput(serializers.Serializer):
    device_key = serializers.UUIDField()
    label = serializers.CharField(max_length=80)
    platform = serializers.ChoiceField(choices=WorkDevice.Platform.choices)


class SharedClaimInput(serializers.Serializer):
    claim_secret = serializers.CharField(max_length=200)


class SharedApproveInput(serializers.Serializer):
    code = serializers.CharField(max_length=20)
    store_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), min_length=1, max_length=30
    )

    def validate_store_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("店舗が重複しています。")
        return value


class DeviceActionInput(serializers.Serializer):
    action = serializers.ChoiceField(choices=["pause", "resume", "revoke"])


class DeviceReceivingInput(serializers.Serializer):
    stores = serializers.ListField(child=serializers.DictField(), min_length=1, max_length=30)

    def validate_stores(self, value):
        parsed = []
        seen = set()
        for row in value:
            try:
                store_id = int(row.get("store_id"))
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError("店舗の指定が正しくありません。") from exc
            if store_id < 1 or store_id in seen or not isinstance(row.get("is_receiving"), bool):
                raise serializers.ValidationError("店舗または受付状態の指定が正しくありません。")
            seen.add(store_id)
            parsed.append((store_id, row["is_receiving"]))
        return parsed


class PersonalDeviceLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [WorkLoginThrottle]

    @extend_schema(request=PersonalLoginInput, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = PersonalLoginInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = authenticate(request, username=data["username"], password=data["password"])
        if not user or not user.is_active:
            raise AuthenticationFailed("ユーザー名またはパスワードが正しくありません。")
        memberships = list(
            operator_memberships(user).filter(
                store_id__in=data["store_ids"], role__in=("manager", "staff")
            )
        )
        if len(memberships) != len(data["store_ids"]):
            raise PermissionDenied("所属していない店舗はこの端末で受けられません。")
        stores_by_id = {membership.store_id: membership.store for membership in memberships}
        stores = [stores_by_id[store_id] for store_id in data["store_ids"]]
        with transaction.atomic():
            existing = WorkDevice.objects.select_for_update().filter(
                device_key=data["device_key"]
            ).first()
            if existing and existing.kind != WorkDevice.Kind.PERSONAL:
                raise ValidationError("この端末は共用端末として登録済みです。")
            device, _ = WorkDevice.objects.update_or_create(
                device_key=data["device_key"],
                defaults={
                    "kind": WorkDevice.Kind.PERSONAL,
                    "label": data["label"],
                    "platform": data["platform"],
                    "owner": user,
                    "approved_by": None,
                    "status": WorkDevice.Status.ACTIVE,
                    "revoked_at": None,
                },
            )
            _replace_subscriptions(device, stores)
            device.credentials.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
            token = _issue_credential(device)
            WorkDeviceEvent.objects.create(device=device, actor=user, action="personal_login")
        return Response({"token": token, "device": _device_payload(device)})


class SharedLinkRequestCreateView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [PublicWorkThrottle]

    @extend_schema(request=SharedLinkInput, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = SharedLinkInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        claim_secret = secrets.token_urlsafe(32)
        expires_at = timezone.now() + LINK_TTL
        with transaction.atomic():
            WorkDeviceLinkRequest.objects.filter(
                device_key=data["device_key"],
                approved_at__isnull=True,
                claimed_at__isnull=True,
                rejected_at__isnull=True,
            ).update(rejected_at=timezone.now())
            while True:
                code = _new_link_code()
                code_hash = _hash_secret(code)
                if not WorkDeviceLinkRequest.objects.filter(code_hash=code_hash).exists():
                    break
            link = WorkDeviceLinkRequest.objects.create(
                device_key=data["device_key"],
                label=data["label"],
                platform=data["platform"],
                code_hash=code_hash,
                claim_secret_hash=_hash_secret(claim_secret),
                expires_at=expires_at,
            )
        return Response(
            {
                "request_id": str(link.pk),
                "code": code,
                "claim_secret": claim_secret,
                "expires_at": expires_at,
            },
            status=status.HTTP_201_CREATED,
        )


class SharedLinkClaimView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [PublicWorkThrottle]

    @extend_schema(request=SharedClaimInput, responses=OpenApiTypes.OBJECT)
    def post(self, request, request_id):
        serializer = SharedClaimInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        now = timezone.now()
        with transaction.atomic():
            link = WorkDeviceLinkRequest.objects.select_for_update().filter(pk=request_id).first()
            if not link or not secrets.compare_digest(
                link.claim_secret_hash,
                _hash_secret(serializer.validated_data["claim_secret"]),
            ):
                raise AuthenticationFailed("連携要求を確認できません。")
            if link.rejected_at or link.expires_at <= now:
                raise ValidationError("連携コードの有効期限が切れています。")
            if not link.approved_at:
                return Response({"status": "pending"}, status=status.HTTP_202_ACCEPTED)
            if link.claimed_at:
                raise ValidationError("この連携コードは使用済みです。")
            stores = list(link.approved_stores.select_related("operation_group"))
            if not stores:
                raise ValidationError("着信対象店舗が設定されていません。")
            device, _ = WorkDevice.objects.update_or_create(
                device_key=link.device_key,
                defaults={
                    "kind": WorkDevice.Kind.SHARED,
                    "label": link.label,
                    "platform": link.platform,
                    "owner": None,
                    "approved_by": link.approved_by,
                    "status": WorkDevice.Status.ACTIVE,
                    "revoked_at": None,
                },
            )
            _replace_subscriptions(device, stores)
            device.credentials.filter(revoked_at__isnull=True).update(revoked_at=now)
            token = _issue_credential(device)
            link.claimed_at = now
            link.save(update_fields=["claimed_at"])
            WorkDeviceEvent.objects.create(
                device=device, actor=link.approved_by, action="shared_claimed"
            )
        return Response({"status": "approved", "token": token, "device": _device_payload(device)})


class OperationWorkDeviceListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        group_id = operation_group_for_request(request)
        stores = Store.objects.filter(operation_group_id=group_id).order_by("name", "id")
        devices = (
            WorkDevice.objects.filter(store_subscriptions__store__operation_group_id=group_id)
            .select_related("owner", "approved_by")
            .distinct()
        )
        return Response(
            {
                "stores": [{"id": store.pk, "name": store.name} for store in stores],
                "devices": [
                    _device_payload(device, operation_group_id=group_id)
                    for device in devices
                ],
            }
        )


class OperationWorkDeviceApproveView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=SharedApproveInput, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = SharedApproveInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        now = timezone.now()
        with transaction.atomic():
            group_id = operation_group_for_request(request)
            stores = scoped_stores(group_id, data["store_ids"], lock=True)
            code = "".join(str(data["code"]).upper().split())
            link = WorkDeviceLinkRequest.objects.select_for_update().filter(
                code_hash=_hash_secret(code),
                approved_at__isnull=True,
                claimed_at__isnull=True,
                rejected_at__isnull=True,
                expires_at__gt=now,
            ).first()
            if not link:
                raise ValidationError("有効な連携コードが見つかりません。")
            link.approved_by = request.user
            link.approved_at = now
            link.save(update_fields=["approved_by", "approved_at"])
            link.approved_stores.set(stores)
        return Response(
            {
                "detail": "共用端末を承認しました。端末側で連携を完了してください。",
                "device_label": link.label,
            }
        )


class OperationWorkDeviceActionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=DeviceActionInput, responses=OpenApiTypes.OBJECT)
    def post(self, request, device_id):
        serializer = DeviceActionInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            group_id = operation_group_for_request(request)
            device = WorkDevice.objects.select_for_update().filter(
                pk=device_id,
                store_subscriptions__store__operation_group_id=group_id,
            ).distinct().first()
            if not device:
                raise ValidationError("端末が見つかりません。")
            if device.store_subscriptions.exclude(store__operation_group_id=group_id).exists():
                raise PermissionDenied("別契約でも利用中の端末は一括変更できません。")
            action = serializer.validated_data["action"]
            if device.status == WorkDevice.Status.REVOKED and action != "revoke":
                raise ValidationError("連携解除済みの端末は再連携が必要です。")
            if action == "revoke":
                device.status = WorkDevice.Status.REVOKED
                device.revoked_at = timezone.now()
                device.credentials.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
            else:
                device.status = (
                    WorkDevice.Status.PAUSED if action == "pause" else WorkDevice.Status.ACTIVE
                )
                device.revoked_at = None
            device.save(update_fields=["status", "revoked_at", "updated_at"])
            WorkDeviceEvent.objects.create(device=device, actor=request.user, action=action)
        return Response(_device_payload(device, operation_group_id=group_id))


class WorkDeviceMeView(APIView):
    authentication_classes = [WorkDeviceAuthentication]
    permission_classes = [IsWorkDevice]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        device = request.work_device
        payload = _device_payload(device)
        entitled_ids = {sub.store_id for sub in entitled_subscriptions(device)}
        payload["stores"] = [row for row in payload["stores"] if row["id"] in entitled_ids]
        return Response(payload)


class WorkDeviceHeartbeatView(APIView):
    authentication_classes = [WorkDeviceAuthentication]
    permission_classes = [IsWorkDevice]

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        device = request.work_device
        device.last_seen_at = timezone.now()
        device.save(update_fields=["last_seen_at", "updated_at"])
        return Response({"last_seen_at": device.last_seen_at})


class WorkDeviceReceivingView(APIView):
    authentication_classes = [WorkDeviceAuthentication]
    permission_classes = [IsWorkDevice]

    @extend_schema(request=DeviceReceivingInput, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = DeviceReceivingInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        device = request.work_device
        entitled = {sub.store_id: sub for sub in entitled_subscriptions(device)}
        requested = dict(serializer.validated_data["stores"])
        if not set(requested).issubset(entitled):
            raise PermissionDenied("利用できない店舗の受付状態は変更できません。")
        with transaction.atomic():
            for store_id, is_receiving in requested.items():
                subscription = entitled[store_id]
                subscription.is_receiving = is_receiving
                subscription.save(update_fields=["is_receiving", "updated_at"])
                WorkDeviceEvent.objects.create(
                    device=device,
                    actor=device.owner or device.approved_by,
                    store_id=store_id,
                    action="receiving_started" if is_receiving else "receiving_stopped",
                )
        return Response(_device_payload(device))


class WorkDeviceCallsView(APIView):
    authentication_classes = [WorkDeviceAuthentication]
    permission_classes = [IsWorkDevice]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        device = request.work_device
        if device.status != WorkDevice.Status.ACTIVE:
            return Response({"calls": []})
        store_ids = [sub.store_id for sub in entitled_subscriptions(device, receiving_only=True)]
        calls = (
            CallLog.objects.filter(
                store_id__in=store_ids,
                status__in=[CallLog.Status.NEW, CallLog.Status.IN_PROGRESS],
            )
            .select_related("store", "customer")
            .order_by("-created_at")[:100]
        )
        return Response(
            {
                "calls": [
                    {
                        "id": call.pk,
                        "contact_id": call.contact_id,
                        "store_id": call.store_id,
                        "store_name": call.store.name,
                        "from_phone": call.from_phone,
                        "customer_name": str(call.customer) if call.customer else None,
                        "status": call.status,
                        "created_at": call.created_at,
                    }
                    for call in calls
                ]
            }
        )


class WorkDeviceRotateTokenView(APIView):
    authentication_classes = [WorkDeviceAuthentication]
    permission_classes = [IsWorkDevice]

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        now = timezone.now()
        with transaction.atomic():
            credential = WorkDeviceCredential.objects.select_for_update().get(
                pk=request.auth.pk
            )
            credential.revoked_at = now
            credential.save(update_fields=["revoked_at"])
            token = _issue_credential(request.work_device)
            WorkDeviceEvent.objects.create(
                device=request.work_device,
                actor=request.work_device.owner or request.work_device.approved_by,
                action="credential_rotated",
            )
        return Response({"token": token, "expires_in_days": TOKEN_TTL.days})
