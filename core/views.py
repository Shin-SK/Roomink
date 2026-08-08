import csv
import io
import logging
import os
import secrets
import uuid
from collections import defaultdict
from datetime import date as date_type, datetime, timedelta

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import ValidationError as DjangoValidationError
from django.views.decorators.csrf import ensure_csrf_cookie
from django.db import transaction
from django.db.models import ProtectedError
from django.utils import timezone
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import parsers, viewsets, status
from rest_framework.decorators import action, api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from twilio.request_validator import RequestValidator

from .models import (
    CallLog, CallNote, Cast, CastAck, CastAdjustment, CastCheckoutExpenseSnapshot,
    CastDailyCheckout, CastExpense, CastExpenseTemplate,
    CastExpenseTemplateHistory, CastNote, Course, Customer,
    CustomerMergeLog, DailySettlement, Discount, Extension, Medium,
    LineNotificationLog, NominationFee, Option, Order, OrderOption, PointLog,
    Room, ShiftAssignment, ShiftConfirmNotificationLog, ShiftRequest, SmsLog,
    SmsTemplate, Store, StorePhoneNumber, UserProfile,
    generate_line_link_code,
)
from .permissions import PastOrderManagerOnlyPermission
from .serializers import (
    CallLogSerializer,
    CallNoteSerializer,
    CastAdjustmentSerializer,
    CastAdjustmentCastSerializer,
    CastCheckoutExpenseSnapshotSerializer,
    CastDailyCheckoutSerializer,
    CastExpenseSerializer,
    CastExpenseTemplateSerializer,
    CastExpenseTemplateHistorySerializer,
    CastNoteSerializer,
    CastNoteCastSerializer,
    CastSerializer,
    PointLogSerializer,
    CastShiftRequestSerializer,
    CastTodayOrderSerializer,
    CourseSerializer,
    CustomerSerializer,
    DiscountSerializer,
    StaffSerializer,
    StaffCreateSerializer,
    StaffUpdateSerializer,
    ExtensionSerializer,
    MediumSerializer,
    NominationFeeSerializer,
    OpShiftRequestSerializer,
    OptionSerializer,
    OrderCreateSerializer,
    OrderSerializer,
    OrderUpdateSerializer,
    RoomSerializer,
    ScheduleResponseSerializer,
    ShiftAssignmentSerializer,
    ShiftConfirmNotificationLogSerializer,
    SmsLogSerializer,
    StorePhoneNumberSerializer,
    build_customer_label,
    build_schedule_data,
    build_room_schedule_data,
)
from .utils.phone import normalize_phone

logger = logging.getLogger(__name__)
from .services.cast_user import ensure_user_profile, update_or_create_cast_with_user
from .services.customer_context import resolve_customer
from .services.pricing import recalculate_order_total
from .services.sales import (
    get_sales_summary, get_sales_csv,
    get_sales_dashboard, get_sales_dashboard_csv,
    get_done_orders_for_business_range,
)
from .services.notify import (
    default_confirmation_preview as _default_sms_preview,
    notify_cast_order,
    notify_order_cancelled,
    notify_order_confirmed,
    notify_customer_account,
)
from .services.customer_invitation import (
    INVALID_INVITATION_MESSAGE,
    activate_customer_invitation,
    get_valid_invitation,
    serialize_invitation_status,
)
from .services.business_datetime import (
    BusinessDateTimeError,
    business_date_for_datetime,
    build_business_interval,
    format_extended_time,
    intervals_overlap,
    parse_extended_time,
)
from .services.order_availability import build_available_order_slots


def document_object_api_view(cls):
    """手書きAPIViewを汎用JSON契約としてOpenAPIへ含める。"""
    for method_name in ("get", "post", "put", "patch", "delete"):
        method = cls.__dict__.get(method_name)
        if method is None:
            continue
        request_schema = None if method_name in ("get", "delete") else OpenApiTypes.OBJECT
        decorated = extend_schema(
            operation_id=f"{cls.__name__}_{method_name}".lower(),
            request=request_schema,
            responses=OpenApiTypes.OBJECT,
        )(method)
        setattr(cls, method_name, decorated)
    return cls


def get_user_store(request):
    """request.user の所属 Store を返す。未設定なら明示エラー。"""
    profile = getattr(request.user, "profile", None)
    if profile is None:
        from rest_framework.exceptions import PermissionDenied
        raise PermissionDenied("ユーザープロフィールが未作成です。管理者に連絡してください。")
    if not hasattr(profile, "store") or profile.store_id is None:
        from rest_framework.exceptions import PermissionDenied
        raise PermissionDenied("所属店舗が設定されていません。管理者に連絡してください。")
    return profile.store


# ──────────────────────────────────────
# Auth
# ──────────────────────────────────────

@extend_schema(operation_id="auth_login", request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def auth_login(request):
    raw_username = request.data.get("username", "")
    # 数字を含む場合のみ電話番号正規化（admin 等の英字ユーザー名はそのまま）
    username = normalize_phone(raw_username) if any(c.isdigit() for c in raw_username) else raw_username
    password = request.data.get("password", "")
    user = authenticate(request, username=username, password=password)
    if user is None:
        return Response(
            {"detail": "ユーザー名またはパスワードが正しくありません"},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    login(request, user)
    return Response({"ok": True, "username": user.username})


@extend_schema(operation_id="auth_logout", request=None, responses=OpenApiTypes.OBJECT)
@api_view(["POST"])
def auth_logout(request):
    logout(request)
    return Response({"ok": True})


@extend_schema(operation_id="auth_password_reset", request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def auth_password_reset(request):
    """公開パスワード再設定は、本人確認手段を導入するまで利用不可。"""
    return Response(
        {"detail": "パスワード再設定は現在利用できません。管理者へお問い合わせください。"},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


@extend_schema(operation_id="auth_me", request=None, responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@ensure_csrf_cookie
def auth_me(request):
    profile = UserProfile.objects.select_related("store").filter(user=request.user).first()
    customer_profiles = list(
        Customer.objects.filter(user=request.user).select_related("store").order_by("id")
    )
    if profile is None and not customer_profiles:
        return Response(
            {"detail": "プロフィールが未作成です。管理者に連絡してください。"},
            status=status.HTTP_403_FORBIDDEN,
        )
    roles = []
    if profile:
        roles.append(profile.role)
    if customer_profiles:
        roles.append("customer")
    store = profile.store if profile else customer_profiles[0].store
    primary_role = profile.role if profile else "customer"
    return Response({
        "id": request.user.id,
        "username": request.user.username,
        "display_name": request.user.first_name or request.user.username,
        "avatar_url": profile.avatar_url if profile else "",
        "store_id": store.id,
        "store_name": store.name,
        "role": primary_role,
        "roles": roles,
    })


@extend_schema(operation_id="auth_profile_update", request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@api_view(["PATCH"])
def auth_profile_update(request):
    user = request.user
    try:
        profile = UserProfile.objects.select_related("store").get(user=user)
    except UserProfile.DoesNotExist:
        return Response(
            {"detail": "プロフィールが未作成です。管理者に連絡してください。"},
            status=status.HTTP_403_FORBIDDEN,
        )
    if "display_name" in request.data:
        user.first_name = request.data["display_name"]
        user.save(update_fields=["first_name"])
    if "avatar_url" in request.data:
        profile.avatar_url = request.data["avatar_url"]
        profile.save(update_fields=["avatar_url"])
    store = profile.store
    return Response({
        "id": user.id,
        "username": user.username,
        "display_name": user.first_name or user.username,
        "avatar_url": profile.avatar_url,
        "store_id": store.id,
        "store_name": store.name,
        "role": profile.role,
    })


@extend_schema(operation_id="csrf_token", request=None, responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def csrf_token_view(request):
    """CSRF cookieを発行するだけのエンドポイント（クロスオリジン用）"""
    return Response({"ok": True})


# ──────────────────────────────────────
# Schedule
# ──────────────────────────────────────

@document_object_api_view
class ScheduleView(APIView):
    def get(self, request):
        date_str = request.query_params.get("date")
        if not date_str:
            return Response(
                {"detail": "date パラメータは必須です（YYYY-MM-DD）"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            d = date_type.fromisoformat(date_str)
        except ValueError:
            return Response(
                {"detail": "date の形式が不正です（YYYY-MM-DD）"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        store = get_user_store(request)
        data = build_schedule_data(store, d)
        serializer = ScheduleResponseSerializer(data)
        return Response(serializer.data)


@document_object_api_view
class RoomScheduleView(APIView):
    def get(self, request):
        date_str = request.query_params.get("date")
        if not date_str:
            return Response(
                {"detail": "date パラメータは必須です（YYYY-MM-DD）"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            d = date_type.fromisoformat(date_str)
        except ValueError:
            return Response(
                {"detail": "date の形式が不正です（YYYY-MM-DD）"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        store = get_user_store(request)
        data = build_room_schedule_data(store, d)
        return Response(data)


# ──────────────────────────────────────
# Order CRUD + status actions
# ──────────────────────────────────────

class OrderViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, PastOrderManagerOnlyPermission]
    queryset = Order.objects.select_related(
        "cast", "room", "customer", "course",
    ).prefetch_related("options").order_by("start")

    filterset_fields = {
        "status": ["exact", "in"],
        "cast": ["exact"],
        "room": ["exact"],
        "customer": ["exact"],
        "start": ["date", "gte", "lte"],
        "end": ["gte", "lte"],
    }
    search_fields = ["memo", "customer__display_name", "customer__phone"]
    ordering_fields = ["start", "end", "created_at", "updated_at"]
    ordering = ["start"]

    def get_queryset(self):
        store = get_user_store(self.request)
        return super().get_queryset().filter(store=store)

    def get_serializer_class(self):
        if self.action == "create":
            return OrderCreateSerializer
        if self.action in ("update", "partial_update"):
            return OrderUpdateSerializer
        return OrderSerializer

    # --- status actions ---

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        order = self.get_object()
        if order.status != Order.Status.REQUESTED:
            return Response(
                {"detail": f"ステータスが {order.get_status_display()} のため承認できません"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.status = Order.Status.CONFIRMED
        order.save(update_fields=["status", "updated_at"])
        notify_order_confirmed(order, created_by=request.user)
        notify_cast_order(order, created_by=request.user)
        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()
        if order.status in (Order.Status.DONE, Order.Status.CANCELLED):
            return Response(
                {"detail": f"ステータスが {order.get_status_display()} のためキャンセルできません"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.status = Order.Status.CANCELLED
        order.save(update_fields=["status", "updated_at"])
        notify_order_cancelled(order, created_by=request.user)
        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=["post"])
    def done(self, request, pk=None):
        """1ステップずつ前進: CONFIRMED/IN_PROGRESS → PENDING_FINALIZE → DONE
        DONE化(会計確定)時は payment_method が CARD/CASH/PAYPAY のいずれかである必要がある"""
        order = self.get_object()
        if order.status in (Order.Status.CONFIRMED, Order.Status.IN_PROGRESS):
            order.status = Order.Status.PENDING_FINALIZE
        elif order.status == Order.Status.PENDING_FINALIZE:
            if order.payment_method not in (
                Order.PaymentMethod.CARD, Order.PaymentMethod.CASH, Order.PaymentMethod.PAYPAY,
            ):
                return Response(
                    {"detail": "支払い方法（カード/現金/PayPay）を選択してから会計確定してください"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            order.status = Order.Status.DONE
        else:
            return Response(
                {"detail": f"ステータスが {order.get_status_display()} のため進められません"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.save(update_fields=["status", "updated_at"])
        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=["post"])
    def apply_extension(self, request, pk=None):
        order = self.get_object()
        store = get_user_store(request)
        extension_id = request.data.get("extension_id")

        if extension_id is None:
            # 解除
            order.extension = None
            order.extension_name = ""
            order.extension_price = 0
        else:
            try:
                ext = Extension.objects.get(pk=extension_id, store=store)
            except Extension.DoesNotExist:
                return Response({"detail": "延長が見つかりません"}, status=status.HTTP_400_BAD_REQUEST)
            order.extension = ext
            order.extension_name = ext.name
            order.extension_price = ext.price

        order.save(update_fields=["extension", "extension_name", "extension_price", "updated_at"])
        recalculate_order_total(order)
        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=["post"])
    def apply_nomination_fee(self, request, pk=None):
        order = self.get_object()
        store = get_user_store(request)
        nomination_fee_id = request.data.get("nomination_fee_id")

        if nomination_fee_id is None:
            order.nomination_fee = None
            order.nomination_fee_name = ""
            order.nomination_fee_price = 0
        else:
            try:
                nf = NominationFee.objects.get(pk=nomination_fee_id, store=store)
            except NominationFee.DoesNotExist:
                return Response({"detail": "指名料が見つかりません"}, status=status.HTTP_400_BAD_REQUEST)
            order.nomination_fee = nf
            order.nomination_fee_name = nf.name
            order.nomination_fee_price = nf.price

        order.save(update_fields=["nomination_fee", "nomination_fee_name", "nomination_fee_price", "updated_at"])
        recalculate_order_total(order)
        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=["post"])
    def apply_discount(self, request, pk=None):
        order = self.get_object()
        store = get_user_store(request)
        discount_id = request.data.get("discount_id")

        if discount_id is None:
            order.discount = None
            order.discount_name = ""
            order.discount_type_snapshot = ""
            order.discount_value_snapshot = 0
            order.discount_amount = 0
        else:
            try:
                dc = Discount.objects.get(pk=discount_id, store=store)
            except Discount.DoesNotExist:
                return Response({"detail": "割引が見つかりません"}, status=status.HTTP_400_BAD_REQUEST)
            order.discount = dc
            order.discount_name = dc.name
            order.discount_type_snapshot = dc.discount_type
            order.discount_value_snapshot = dc.value

        order.save(update_fields=[
            "discount", "discount_name", "discount_type_snapshot", "discount_value_snapshot", "updated_at",
        ])
        recalculate_order_total(order)
        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=["post"])
    def apply_medium(self, request, pk=None):
        order = self.get_object()
        store = get_user_store(request)
        medium_id = request.data.get("medium_id")

        if medium_id is None:
            order.medium = None
            order.medium_name = ""
        else:
            try:
                med = Medium.objects.get(pk=medium_id, store=store)
            except Medium.DoesNotExist:
                return Response({"detail": "媒体が見つかりません"}, status=status.HTTP_400_BAD_REQUEST)
            order.medium = med
            order.medium_name = med.name

        order.save(update_fields=["medium", "medium_name", "updated_at"])
        return Response(OrderSerializer(order).data)


# ──────────────────────────────────────
# Cast Today / ACK
# ──────────────────────────────────────

@document_object_api_view
class CastTodayView(APIView):
    """GET /api/cast/today/?date=YYYY-MM-DD — キャスト本人の当日予約一覧"""

    def get(self, request):
        cast = getattr(request.user, "cast_profile", None)
        if cast is None:
            return Response(
                {"detail": "このユーザーにキャストが紐づいていません"},
                status=status.HTTP_403_FORBIDDEN,
            )

        date_str = request.query_params.get("date")
        if not date_str:
            return Response(
                {"detail": "date パラメータは必須です（YYYY-MM-DD）"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            d = date_type.fromisoformat(date_str)
        except ValueError:
            return Response(
                {"detail": "date の形式が不正です（YYYY-MM-DD）"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        orders = (
            Order.objects
            .filter(cast=cast, start__date=d)
            .exclude(status__in=[Order.Status.DONE, Order.Status.CANCELLED])
            .select_related("room", "customer", "course")
            .order_by("start")
        )

        acked_ids = set(
            CastAck.objects
            .filter(order__in=orders, acked_at__isnull=False)
            .values_list("order_id", flat=True)
        )

        # シフト情報
        shift = (
            ShiftAssignment.objects
            .filter(cast=cast, date=d)
            .select_related("room")
            .first()
        )

        data = []
        for o in orders:
            data.append({
                "id": o.id,
                "start": o.start,
                "end": o.end,
                "status": o.status,
                "room_id": o.room_id,
                "room_name": o.room.name,
                "customer_label": build_customer_label(o.customer),
                "course_name": o.course_name,
                "course_price": o.course_price,
                "memo": o.memo,
                "is_unconfirmed": o.id not in acked_ids,
            })

        serializer = CastTodayOrderSerializer(data, many=True)

        return Response({
            "cast_name": cast.name,
            "avatar_url": cast.avatar_url,
            "date": d.isoformat(),
            "shift": {
                "start_time": str(shift.start_time)[:5] if shift else None,
                "end_time": str(shift.end_time)[:5] if shift else None,
                "room_name": shift.room.name if shift else None,
            } if shift else None,
            "total_orders": len(data),
            "unconfirmed_count": sum(1 for o in data if o["is_unconfirmed"]),
            "orders": serializer.data,
            "line_linked": cast.line_user_id is not None,
            "line_link_code": cast.line_link_code,
            "line_add_friend_url": cast.store.line_add_friend_url if cast.store else "",
        })


def _compute_cast_done_sales(cast, d):
    """指定キャスト・指定日のDONE注文を集計し、売上/給与見込みを返す（CastTodaySalesView/CastCheckoutViewで共用）"""
    import math

    done_orders = get_done_orders_for_business_range(cast.store, d, d).filter(cast=cast)

    done_count = done_orders.count()
    total_sales = sum(o.total_price for o in done_orders)
    course_sales = sum(o.course_price for o in done_orders)
    options_sales = sum(o.options_price for o in done_orders)

    course_back = math.floor(course_sales * cast.course_back_rate / 100)
    option_back = options_sales if cast.option_fullback_enabled else 0
    estimated_pay = course_back + option_back

    return {
        "done_count": done_count,
        "total_sales": total_sales,
        "estimated_pay": estimated_pay,
        "course_sales": course_sales,
        "options_sales": options_sales,
    }


def _compute_payment_fee_estimate(store, cast, d):
    """指定キャスト・指定日のDONE注文について、決済方法別の手数料率（参考値）から
    手数料見込み/手数料差引後売上見込みを計算する。CastCheckoutView専用。
    給与確定・支払い処理には一切接続しない参考値。"""
    import math
    from .services.sales import payment_fee_rates

    done_orders = get_done_orders_for_business_range(store, d, d).filter(cast=cast)
    fee_rates = payment_fee_rates(store)

    total_sales = 0
    fee_estimate = 0
    for o in done_orders:
        total_sales += o.total_price
        rate = fee_rates.get(o.payment_method, 0)
        fee_estimate += math.floor(o.total_price * rate / 100)

    return {
        "payment_fee_estimate": fee_estimate,
        "net_sales_after_payment_fee": total_sales - fee_estimate,
    }


@document_object_api_view
class CastTodaySalesView(APIView):
    """GET /api/cast/today-sales/ — キャスト本人の本日の売上/給与見込み（DONEのみ）"""

    def get(self, request):
        cast = getattr(request.user, "cast_profile", None)
        if cast is None:
            return Response(
                {"detail": "このユーザーにキャストが紐づいていません"},
                status=status.HTTP_403_FORBIDDEN,
            )

        today = business_date_for_datetime(timezone.now(), cast.store.timezone)
        return Response(_compute_cast_done_sales(cast, today))


@document_object_api_view
class CastCheckoutView(APIView):
    """
    GET /api/cast/checkout/ — 本日の見込み・固定雑費テンプレ・既存提出内容を返す
    POST /api/cast/checkout/ — 退勤提出（当日提出済み・確認済みの場合は不可。差戻し後は再提出可）

    Phase 3-A: 給与確定ではなく、退勤提出時点の見込みスナップショット + manager確認の土台。
    """

    def get(self, request):
        cast = getattr(request.user, "cast_profile", None)
        if cast is None:
            return Response(
                {"detail": "このユーザーにキャストが紐づいていません"},
                status=status.HTTP_403_FORBIDDEN,
            )

        today = business_date_for_datetime(timezone.now(), cast.store.timezone)
        sales = _compute_cast_done_sales(cast, today)
        fee = _compute_payment_fee_estimate(cast.store, cast, today)

        templates = CastExpenseTemplate.objects.filter(cast=cast, is_active=True).order_by("id")
        template_data = [
            {"id": t.id, "name": t.name, "amount": t.amount, "memo": t.memo}
            for t in templates
        ]

        existing = CastDailyCheckout.objects.filter(cast=cast, date=today).select_related("reviewed_by").prefetch_related("expense_snapshots").first()

        return Response({
            "date": today.isoformat(),
            **sales,
            **fee,
            "expense_templates": template_data,
            "checkout": CastDailyCheckoutSerializer(existing).data if existing else None,
            "can_submit": existing is None or existing.status == CastDailyCheckout.Status.RETURNED,
        })

    def post(self, request):
        cast = getattr(request.user, "cast_profile", None)
        if cast is None:
            return Response(
                {"detail": "このユーザーにキャストが紐づいていません"},
                status=status.HTTP_403_FORBIDDEN,
            )

        today = business_date_for_datetime(timezone.now(), cast.store.timezone)
        existing = CastDailyCheckout.objects.filter(cast=cast, date=today).first()
        if existing is not None and existing.status != CastDailyCheckout.Status.RETURNED:
            return Response(
                {"detail": "本日はすでに退勤提出済みです"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            actual_take_home_amount = int(request.data.get("actual_take_home_amount") or 0)
        except (TypeError, ValueError):
            return Response(
                {"detail": "実際の持ち帰り金額の形式が不正です"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if actual_take_home_amount < 0:
            return Response(
                {"detail": "実際の持ち帰り金額は0以上で入力してください"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        checklist_json = request.data.get("checklist_json", {})
        if not isinstance(checklist_json, dict):
            return Response(
                {"detail": "checklist_json の形式が不正です"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cast_memo = request.data.get("cast_memo", "") or ""

        sales = _compute_cast_done_sales(cast, today)
        fee = _compute_payment_fee_estimate(cast.store, cast, today)
        templates = list(CastExpenseTemplate.objects.filter(cast=cast, is_active=True).order_by("id"))

        with transaction.atomic():
            if existing is not None:
                instance = existing
                instance.expense_snapshots.all().delete()
            else:
                instance = CastDailyCheckout(store=cast.store, cast=cast, date=today)

            instance.done_count = sales["done_count"]
            instance.total_sales = sales["total_sales"]
            instance.estimated_pay = sales["estimated_pay"]
            instance.course_sales = sales["course_sales"]
            instance.options_sales = sales["options_sales"]
            instance.payment_fee_estimate = fee["payment_fee_estimate"]
            instance.net_sales_after_payment_fee = fee["net_sales_after_payment_fee"]
            instance.actual_take_home_amount = actual_take_home_amount
            instance.checklist_json = checklist_json
            instance.cast_memo = cast_memo
            instance.status = CastDailyCheckout.Status.SUBMITTED
            instance.submitted_at = timezone.now()
            instance.save()

            CastCheckoutExpenseSnapshot.objects.bulk_create([
                CastCheckoutExpenseSnapshot(
                    checkout=instance, template=t, name=t.name, amount=t.amount, memo=t.memo,
                )
                for t in templates
            ])

        instance.refresh_from_db()
        return Response(
            CastDailyCheckoutSerializer(instance).data,
            status=status.HTTP_201_CREATED,
        )


def _serialize_shift_for_confirm(shift):
    if shift is None:
        return None
    return {
        "id": shift.id,
        "date": shift.date.isoformat(),
        "start_time": str(shift.start_time)[:5],
        "end_time": str(shift.end_time)[:5],
        "room_name": shift.room.name if shift.room_id else None,
        "confirmed_at": shift.confirmed_at,
    }


@document_object_api_view
class CastShiftConfirmView(APIView):
    """
    GET /api/cast/shift-confirm/ — 本日 or 直近未来のShiftAssignmentと出勤確認状況を返す
    POST /api/cast/shift-confirm/ — 出勤確認する（{"shift_id": <id>}）

    Phase 3-B-1: 出勤確認の状態保存 + 表示のみ。通知・リマインド・出勤打刻（clocked_in_at）とは無関係。
    """

    def _find_target_shift(self, cast):
        today = timezone.localdate()
        return (
            ShiftAssignment.objects
            .filter(cast=cast, date__gte=today)
            .select_related("room")
            .order_by("date", "start_time")
            .first()
        )

    def get(self, request):
        cast = getattr(request.user, "cast_profile", None)
        if cast is None:
            return Response(
                {"detail": "このユーザーにキャストが紐づいていません"},
                status=status.HTTP_403_FORBIDDEN,
            )

        shift = self._find_target_shift(cast)
        today = timezone.localdate()
        return Response({
            "shift": _serialize_shift_for_confirm(shift),
            "is_today": bool(shift and shift.date == today),
        })

    def post(self, request):
        cast = getattr(request.user, "cast_profile", None)
        if cast is None:
            return Response(
                {"detail": "このユーザーにキャストが紐づいていません"},
                status=status.HTTP_403_FORBIDDEN,
            )

        shift_id = request.data.get("shift_id")
        shift = ShiftAssignment.objects.select_related("room").filter(pk=shift_id, cast=cast).first()
        if shift is None:
            return Response(
                {"detail": "対象のシフトが見つかりません"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if shift.confirmed_at is None:
            shift.confirmed_at = timezone.now()
            shift.save(update_fields=["confirmed_at"])

        today = timezone.localdate()
        return Response({
            "shift": _serialize_shift_for_confirm(shift),
            "is_today": shift.date == today,
        })


@document_object_api_view
class CastAckView(APIView):
    """POST /api/cast/orders/{id}/ack/ — キャストが予約を確認"""

    def post(self, request, pk):
        cast = getattr(request.user, "cast_profile", None)
        if cast is None:
            return Response(
                {"detail": "このユーザーにキャストが紐づいていません"},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            order = Order.objects.select_related("room", "customer", "course").get(pk=pk)
        except Order.DoesNotExist:
            return Response(
                {"detail": "予約が見つかりません"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if order.cast_id != cast.id:
            return Response(
                {"detail": "この予約は別のキャストに割り当てられています"},
                status=status.HTTP_403_FORBIDDEN,
            )

        from django.utils import timezone
        ack, _ = CastAck.objects.get_or_create(order=order)
        ack.acked_at = timezone.now()
        ack.save(update_fields=["acked_at"])

        return Response({
            "id": order.id,
            "start": order.start,
            "end": order.end,
            "status": order.status,
            "room_id": order.room_id,
            "room_name": order.room.name,
            "customer_label": build_customer_label(order.customer),
            "course_name": order.course_name,
            "course_price": order.course_price,
            "memo": order.memo,
            "is_unconfirmed": False,
        })


@document_object_api_view
class OpOrderCastAckView(APIView):
    """POST /api/op/orders/{id}/cast-ack/ — 運営が代理でキャスト確認済みにする"""

    def post(self, request, pk):
        store = get_user_store(request)
        try:
            order = Order.objects.select_related("room", "customer", "course").get(pk=pk)
        except Order.DoesNotExist:
            return Response(
                {"detail": "予約が見つかりません"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if order.store_id != store.id:
            return Response(
                {"detail": "この予約は別店舗です"},
                status=status.HTTP_403_FORBIDDEN,
            )

        ack, _ = CastAck.objects.get_or_create(order=order)
        if ack.acked_at is None:
            ack.acked_at = timezone.now()
            ack.save(update_fields=["acked_at"])

        return Response({
            "id": order.id,
            "start": order.start,
            "end": order.end,
            "status": order.status,
            "room_id": order.room_id,
            "room_name": order.room.name,
            "customer_label": build_customer_label(order.customer),
            "course_name": order.course_name,
            "course_price": order.course_price,
            "memo": order.memo,
            "is_unconfirmed": False,
        })


# ──────────────────────────────────────
# Customer — signup / mypage / booking
# ──────────────────────────────────────

@document_object_api_view
class StoreListPublicView(APIView):
    """GET /api/cu/store-list/ — 全店舗一覧（サインアップ用、認証不要）"""
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        stores = Store.objects.order_by("id")
        return Response({
            "stores": [
                {"store_id": s.id, "store_name": s.name}
                for s in stores
            ]
        })


@document_object_api_view
class CustomerStoresView(APIView):
    """GET /api/cu/stores/ — 顧客が所属する店舗一覧"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        customers = Customer.objects.filter(
            user=request.user,
        ).select_related("store")
        if not customers.exists():
            return Response(
                {"detail": "このユーザーに顧客プロフィールが紐づいていません"},
                status=status.HTTP_403_FORBIDDEN,
            )
        stores = [
            {"store_id": c.store_id, "store_name": c.store.name, "logo_url": ""}
            for c in customers
        ]
        return Response({"stores": stores})


@extend_schema(operation_id="customer_signup", request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def customer_signup(request):
    """本人確認のない公開登録は停止し、予約確定時の招待に限定する。"""
    return Response(
        {"detail": "新規登録は予約確定後にSMSで届く案内から行ってください。"},
        status=status.HTTP_410_GONE,
    )


@extend_schema(operation_id="customer_login", request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def customer_login(request):
    phone = normalize_phone((request.data.get("phone") or "").strip())
    password = request.data.get("password", "")
    failure = {"detail": "電話番号またはパスワードが正しくありません"}
    if not phone or not password:
        return Response(failure, status=status.HTTP_401_UNAUTHORIZED)

    candidates = Customer.objects.filter(
        user__isnull=False,
        phone__endswith=phone[-4:],
    ).select_related("user")
    users = {
        customer.user_id: customer.user
        for customer in candidates
        if normalize_phone(customer.phone) == phone
    }
    if len(users) != 1:
        # 存在しない電話番号でもpassword hash計算を行い、応答時間による列挙を抑える。
        authenticate(
            request,
            username="__roomink_customer_login_dummy__",
            password=password,
        )
        return Response(failure, status=status.HTTP_401_UNAUTHORIZED)

    candidate = next(iter(users.values()))
    user = authenticate(request, username=candidate.username, password=password)
    if user is None:
        return Response(failure, status=status.HTTP_401_UNAUTHORIZED)
    login(request, user)
    return Response({"ok": True})


@extend_schema(
    operation_id="customer_activation_preview",
    request=OpenApiTypes.OBJECT,
    responses=OpenApiTypes.OBJECT,
)
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def customer_activation_preview(request):
    invitation = get_valid_invitation(request.data.get("token", ""))
    if invitation is None:
        return Response(
            {"detail": INVALID_INVITATION_MESSAGE},
            status=status.HTTP_400_BAD_REQUEST,
        )
    digits = normalize_phone(invitation.customer.phone)
    return Response({
        "masked_phone": f"***{digits[-4:]}" if digits else "***",
        "expires_at": invitation.expires_at,
    })


@extend_schema(
    operation_id="customer_activation_complete",
    request=OpenApiTypes.OBJECT,
    responses=OpenApiTypes.OBJECT,
)
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def customer_activate(request):
    try:
        _, next_path = activate_customer_invitation(
            request,
            request.data.get("token", ""),
            request.data.get("password", ""),
            request.data.get("password_confirm", ""),
        )
    except DjangoValidationError as exc:
        messages = list(exc.messages)
        return Response(
            {"detail": messages[0] if len(messages) == 1 else messages},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response({"ok": True, "next": next_path})


@document_object_api_view
class CustomerMypageView(APIView):
    """GET /api/cu/mypage/ — 顧客マイページ"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        customer = resolve_customer(request)

        from django.db.models import Count, Sum
        from django.utils import timezone

        now = timezone.now()

        # ── 次回予約 ──
        next_order = (
            Order.objects
            .filter(
                customer=customer,
                status__in=[Order.Status.REQUESTED, Order.Status.CONFIRMED, Order.Status.IN_PROGRESS],
                start__gt=now,
            )
            .select_related("cast", "course")
            .order_by("start")
            .first()
        )
        next_reservation = None
        if next_order:
            next_reservation = {
                "id": next_order.id,
                "start": next_order.start,
                "end": next_order.end,
                "status": next_order.status,
                "cast_name": next_order.cast.name,
                "course_name": next_order.course_name,
                "total_price": next_order.total_price,
            }

        # ── 推しセラピスト（直近指名キャスト 1名）──
        fav_cast_id = (
            Order.objects
            .filter(customer=customer, status__in=[Order.Status.DONE, Order.Status.CONFIRMED])
            .values("cast_id")
            .annotate(cnt=Count("id"))
            .order_by("-cnt")
            .values_list("cast_id", flat=True)
            .first()
        )
        favorites = []
        if fav_cast_id:
            fav_cast = Cast.objects.filter(pk=fav_cast_id).first()
            if fav_cast:
                fav_agg = Order.objects.filter(
                    customer=customer, cast=fav_cast, status=Order.Status.DONE,
                ).aggregate(visit_count=Count("id"), total_spend=Sum("total_price"))
                favorites.append({
                    "id": fav_cast.id,
                    "name": fav_cast.name,
                    "avatar_url": fav_cast.avatar_url,
                    "visit_count": fav_agg["visit_count"],
                    "total_spend": fav_agg["total_spend"] or 0,
                })

        # ── おすすめ（store 内キャスト最大3名、推し除外）──
        rec_qs = Cast.objects.filter(store=customer.store).exclude(pk=fav_cast_id or 0).order_by("name")[:3]
        recommended = [
            {"id": c.id, "name": c.name, "avatar_url": c.avatar_url, "introduction": c.introduction}
            for c in rec_qs
        ]

        # ── 来店履歴 ──
        history_qs = (
            Order.objects
            .filter(customer=customer)
            .exclude(status=Order.Status.CANCELLED)
            .select_related("cast", "course")
            .prefetch_related("options")
            .order_by("-start")[:10]
        )
        history = []
        for o in history_qs:
            history.append({
                "id": o.id,
                "date": o.start.date().isoformat(),
                "cast_name": o.cast.name,
                "course_name": o.course_name,
                "total_price": o.total_price,
                "status": o.status,
            })

        # ── 累計 ──
        done_agg = Order.objects.filter(
            customer=customer, status=Order.Status.DONE,
        ).aggregate(total_visits=Count("id"), total_spend=Sum("total_price"))
        total_visits = done_agg["total_visits"]
        total_spend = done_agg["total_spend"] or 0

        return Response({
            "customer": {
                "display_name": customer.display_name or customer.phone,
                "phone": customer.phone,
                "total_visits": total_visits,
                "total_spend": total_spend,
            },
            "next_reservation": next_reservation,
            "favorites": favorites,
            "recommended": recommended,
            "history": history,
        })


@document_object_api_view
class CustomerAvailableSlotsView(APIView):
    """GET /api/cu/available-slots/?cast={id}&date={YYYY-MM-DD}"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        customer = resolve_customer(request)
        store = customer.store

        cast_id = request.query_params.get("cast")
        date_str = request.query_params.get("date")
        if not cast_id or not date_str:
            return Response(
                {"detail": "cast と date は必須です"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            d = date_type.fromisoformat(date_str)
        except ValueError:
            return Response(
                {"detail": "date の形式が不正です（YYYY-MM-DD）"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cast = Cast.objects.filter(store=store, pk=cast_id).first()
        if cast is None:
            return Response({"date": date_str, "cast_id": int(cast_id), "cast_name": "", "slots": []})

        slots = build_available_order_slots(store, cast, d)

        return Response({
            "date": date_str,
            "cast_id": cast.id,
            "cast_name": cast.name,
            "slots": slots,
        })


@document_object_api_view
class CustomerBookingOptionsView(APIView):
    """GET /api/cu/booking/options/ — 予約フォーム選択肢"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        customer = resolve_customer(request)
        store = customer.store
        casts = [{"id": c.id, "name": c.name, "avatar_url": c.avatar_url, "introduction": c.introduction} for c in Cast.objects.filter(store=store).order_by("name")]
        courses_qs = Course.objects.filter(store=store).prefetch_related("target_casts").order_by("id")
        courses = []
        for c in courses_qs:
            tc_ids = list(c.target_casts.values_list("id", flat=True))
            courses.append({
                "id": c.id, "name": c.name, "duration": c.duration,
                "price": c.price, "target_cast_ids": tc_ids,
            })
        options = [{"id": o.id, "name": o.name, "price": o.price} for o in Option.objects.filter(store=store).order_by("id")]

        return Response({"casts": casts, "courses": courses, "options": options})


@document_object_api_view
class CustomerBookingCreateView(APIView):
    """POST /api/cu/bookings/ — 顧客からの予約申請"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        customer = resolve_customer(request)

        data = request.data.copy()
        data["customer"] = customer.id

        serializer = OrderCreateSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


@document_object_api_view
class CustomerReservationDetailView(APIView):
    """GET /api/cu/reservations/<id>/ — 顧客向け予約詳細"""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        customer = resolve_customer(request)
        try:
            order = Order.objects.select_related(
                "cast", "room", "course", "customer", "extension",
                "nomination_fee", "discount", "medium",
            ).prefetch_related("options").get(pk=pk, customer=customer)
        except Order.DoesNotExist:
            return Response(
                {"detail": "予約が見つかりません"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({
            "id": order.id,
            "status": order.status,
            "status_display": order.get_status_display(),
            "start": order.start,
            "end": order.end,
            "cast_name": order.cast.name if order.cast else "",
            "cast_avatar_url": order.cast.avatar_url if order.cast else "",
            "room_name": order.room.name if order.room else "",
            "course_name": order.course_name,
            "course_price": order.course_price,
            "options": [o.name for o in order.options.all()],
            "options_price": order.options_price,
            "extension_name": order.extension_name,
            "extension_price": order.extension_price,
            "nomination_fee_name": order.nomination_fee_name,
            "nomination_fee_price": order.nomination_fee_price,
            "discount_name": order.discount_name,
            "discount_amount": order.discount_amount,
            "total_price": order.total_price,
            "memo": order.memo,
            "store_name": order.store.name if order.store_id else "",
            "created_at": order.created_at,
        })


# ──────────────────────────────────────
# Shift / Customer / Master
# ──────────────────────────────────────

class ShiftAssignmentViewSet(viewsets.ModelViewSet):
    queryset = ShiftAssignment.objects.select_related("cast", "room").order_by(
        "date", "start_time",
    )
    serializer_class = ShiftAssignmentSerializer
    filterset_fields = {
        "date": ["exact", "gte", "lte"],
        "cast": ["exact"],
        "room": ["exact"],
    }
    ordering_fields = ["date", "start_time"]
    ordering = ["date", "start_time"]

    def get_queryset(self):
        store = get_user_store(self.request)
        return super().get_queryset().filter(store=store)

    def get_serializer_context(self):
        # store は read_only のため、シリアライザの重複チェック用に context で渡す
        context = super().get_serializer_context()
        if self.request.user.is_authenticated:
            context["store"] = get_user_store(self.request)
        return context

    def perform_create(self, serializer):
        serializer.save(store=get_user_store(self.request))

    @action(detail=True, methods=["post"], url_path="clock-in")
    def clock_in(self, request, pk=None):
        shift = self.get_object()
        now = timezone.now()
        today = timezone.localdate()
        if shift.date < today:
            # 過去日のレトロ記録: シフト開始時刻を打刻時刻として扱う
            naive = datetime.combine(shift.date, shift.start_time)
            tz = timezone.get_current_timezone()
            shift.clocked_in_at = timezone.make_aware(naive, tz)
        else:
            shift.clocked_in_at = now
        # 当欠状態のまま出勤済みになる矛盾を避ける
        shift.is_absent = False
        shift.save(update_fields=["clocked_in_at", "is_absent"])
        return Response(self.get_serializer(shift).data)

    @action(detail=True, methods=["post"], url_path="clear-clock-in")
    def clear_clock_in(self, request, pk=None):
        shift = self.get_object()
        shift.clocked_in_at = None
        shift.save(update_fields=["clocked_in_at"])
        return Response(self.get_serializer(shift).data)


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.order_by("id")
    serializer_class = CustomerSerializer
    filterset_fields = {
        "flag": ["exact"],
        "phone": ["exact"],
    }
    search_fields = ["display_name", "phone"]
    ordering_fields = ["id", "display_name"]
    ordering = ["id"]

    def get_queryset(self):
        store = get_user_store(self.request)
        return super().get_queryset().filter(store=store)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        customers_data = response.data
        if isinstance(customers_data, dict) and "results" in customers_data:
            items = customers_data["results"]
        elif isinstance(customers_data, list):
            items = customers_data
        else:
            return response

        # 重複候補カウントを一括計算
        phone_map = {}
        name_map = {}
        for item in items:
            digits = normalize_phone(item.get("phone", ""))
            if digits:
                phone_map.setdefault(digits, []).append(item["id"])
            name = (item.get("display_name") or "").strip().lower()
            if name:
                name_map.setdefault(name, []).append(item["id"])

        dup_counts = {}
        for ids in phone_map.values():
            if len(ids) > 1:
                for cid in ids:
                    dup_counts[cid] = dup_counts.get(cid, 0) + len(ids) - 1
        for ids in name_map.values():
            if len(ids) > 1:
                for cid in ids:
                    dup_counts[cid] = dup_counts.get(cid, 0) + len(ids) - 1

        for item in items:
            item["duplicate_count"] = dup_counts.get(item["id"], 0)

        return response

    def perform_create(self, serializer):
        serializer.save(store=get_user_store(self.request))

    @action(detail=False, methods=["get"], url_path="check-duplicate")
    def check_duplicate(self, request):
        """GET /api/customers/check-duplicate/?phone=...&name=... — 新規作成前の重複チェック"""
        store = get_user_store(request)
        phone = request.query_params.get("phone", "").strip()
        name = request.query_params.get("name", "").strip()

        phone_digits = normalize_phone(phone) if phone else ""
        name_lower = name.lower() if name else ""

        qs = Customer.objects.filter(store=store)
        candidates = []
        seen = set()

        if phone_digits:
            for c in qs:
                c_digits = normalize_phone(c.phone)
                if c_digits and c_digits == phone_digits and c.pk not in seen:
                    seen.add(c.pk)
                    candidates.append({"id": c.id, "phone": c.phone, "display_name": c.display_name, "flag": c.flag, "ban_type": c.ban_type, "reason": "電話番号一致"})

        if name_lower:
            for c in qs:
                c_name = (c.display_name or "").strip().lower()
                if c_name and c_name == name_lower and c.pk not in seen:
                    seen.add(c.pk)
                    candidates.append({"id": c.id, "phone": c.phone, "display_name": c.display_name, "flag": c.flag, "ban_type": c.ban_type, "reason": "名前一致"})

        return Response(candidates[:10])

    @action(detail=True, methods=["post"], url_path="merge")
    def merge(self, request, pk=None):
        """POST /api/customers/{keep_id}/merge/ { merge_id }
        keep_id を残し、merge_id の参照を keep_id に寄せてから merge_id を削除する。
        """
        profile = getattr(request.user, "profile", None)
        if profile is None or profile.role != "manager":
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("この操作はマネージャーのみ利用可能です")

        keep = self.get_object()
        store = get_user_store(request)
        merge_id = request.data.get("merge_id")
        if not merge_id:
            return Response({"detail": "merge_id は必須です"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            merge_customer = Customer.objects.get(pk=merge_id, store=store)
        except Customer.DoesNotExist:
            return Response({"detail": "統合対象の顧客が見つかりません"}, status=status.HTTP_404_NOT_FOUND)

        if keep.pk == merge_customer.pk:
            return Response({"detail": "同じ���客には統合できません"}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # スナップショット（削除前に保存）
            snap_name = merge_customer.display_name or ""
            snap_phone = merge_customer.phone or ""
            snap_id = merge_customer.pk

            # 1) FK 付け替え
            orders_moved = Order.objects.filter(customer=merge_customer).update(customer=keep)
            calls_moved = CallLog.objects.filter(customer=merge_customer).update(customer=keep)

            # 2) 空欄補完
            if not keep.display_name and merge_customer.display_name:
                keep.display_name = merge_customer.display_name
            if not keep.phone and merge_customer.phone:
                keep.phone = merge_customer.phone

            # 3) flag / ban_type — 強い方を優先
            flag_priority = {"BAN": 3, "ATTENTION": 2, "NONE": 1}
            if flag_priority.get(merge_customer.flag, 0) > flag_priority.get(keep.flag, 0):
                keep.flag = merge_customer.flag
            ban_priority = {"STORE_BAN": 3, "CAST_NG": 2, "NONE": 1}
            if ban_priority.get(merge_customer.ban_type, 0) > ban_priority.get(keep.ban_type, 0):
                keep.ban_type = merge_customer.ban_type

            # 4) user 引き継ぎ
            if not keep.user and merge_customer.user:
                keep.user = merge_customer.user
                merge_customer.user = None
                merge_customer.save(update_fields=["user"])

            keep.save()

            # 5) merge 顧客を削除
            merge_customer.delete()

            # 6) 監査ログ
            CustomerMergeLog.objects.create(
                store=store,
                keep_customer=keep,
                merged_customer_id=snap_id,
                merged_customer_name=snap_name,
                merged_customer_phone=snap_phone,
                orders_moved=orders_moved,
                call_logs_moved=calls_moved,
                executed_by=request.user,
            )

        return Response({
            "ok": True,
            "keep_id": keep.pk,
            "merged_id": int(merge_id),
        })

    @action(detail=True, methods=["get"], url_path="duplicates")
    def duplicates(self, request, pk=None):
        """GET /api/customers/{id}/duplicates/ — 重複候補を返す"""
        customer = self.get_object()
        store = get_user_store(request)
        qs = Customer.objects.filter(store=store).exclude(pk=customer.pk)

        candidates = []
        seen = set()

        phone_digits = normalize_phone(customer.phone)
        name_lower = (customer.display_name or "").strip().lower()

        # 1) phone 数字一致
        if phone_digits:
            for c in qs:
                c_digits = normalize_phone(c.phone)
                if c_digits and c_digits == phone_digits and c.pk not in seen:
                    seen.add(c.pk)
                    candidates.append({"customer": c, "reason": "電話番号一致"})

        # 2) display_name 一致（空でない場合のみ）
        if name_lower:
            for c in qs:
                c_name = (c.display_name or "").strip().lower()
                if c_name and c_name == name_lower and c.pk not in seen:
                    seen.add(c.pk)
                    candidates.append({"customer": c, "reason": "名前一致"})

        result = []
        for item in candidates[:20]:
            c = item["customer"]
            result.append({
                "id": c.id,
                "phone": c.phone,
                "display_name": c.display_name,
                "flag": c.flag,
                "ban_type": c.ban_type,
                "memo": (c.memo or "")[:50],
                "reason": item["reason"],
            })

        return Response(result)


class CastViewSet(viewsets.ModelViewSet):
    queryset = Cast.objects.order_by("name")
    serializer_class = CastSerializer

    def get_queryset(self):
        store = get_user_store(self.request)
        return super().get_queryset().filter(store=store)

    def perform_create(self, serializer):
        cast = serializer.save(store=get_user_store(self.request))
        if cast.user:
            ensure_user_profile(cast.user, cast.store, role=UserProfile.Role.CAST)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            self.perform_destroy(instance)
        except ProtectedError:
            return Response(
                {"detail": "このキャストは予約やシフトで使用されているため削除できません"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class StaffViewSet(viewsets.ViewSet):
    """スタッフ (role=staff/manager) の CRUD"""

    queryset = UserProfile.objects.none()
    serializer_class = StaffSerializer

    def list(self, request):
        store = get_user_store(request)
        qs = UserProfile.objects.filter(
            store=store, role__in=["staff", "manager"],
        ).select_related("user").order_by("user__username")
        serializer = StaffSerializer(qs, many=True)
        return Response(serializer.data)

    def create(self, request):
        store = get_user_store(request)
        serializer = StaffCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = serializer.save(store=store)
        return Response(StaffSerializer(profile).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        store = get_user_store(request)
        try:
            profile = UserProfile.objects.select_related("user").get(
                pk=pk, store=store, role__in=["staff", "manager"],
            )
        except UserProfile.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = StaffUpdateSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        profile = serializer.save()
        return Response(StaffSerializer(profile).data)

    def destroy(self, request, pk=None):
        store = get_user_store(request)
        try:
            profile = UserProfile.objects.select_related("user").get(
                pk=pk, store=store, role__in=["staff", "manager"],
            )
        except UserProfile.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if profile.user == request.user:
            return Response(
                {"detail": "自分自身は削除できません"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = profile.user
        profile.delete()
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CourseViewSet(viewsets.ModelViewSet):
    queryset = Course.objects.order_by("id")
    serializer_class = CourseSerializer

    def get_queryset(self):
        store = get_user_store(self.request)
        return super().get_queryset().filter(store=store)

    def perform_create(self, serializer):
        serializer.save(store=get_user_store(self.request))

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            self.perform_destroy(instance)
        except ProtectedError:
            return Response(
                {"detail": "このコースは予約で使用されているため削除できません"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class StorePhoneNumberViewSet(viewsets.ModelViewSet):
    queryset = StorePhoneNumber.objects.order_by("id")
    serializer_class = StorePhoneNumberSerializer

    def get_queryset(self):
        store = get_user_store(self.request)
        return super().get_queryset().filter(store=store)

    def perform_create(self, serializer):
        serializer.save(store=get_user_store(self.request))

    def destroy(self, request, *args, **kwargs):
        # 削除は使わない。無効化は PATCH is_active=False で行う
        return Response(
            {"detail": "削除は使用できません。無効化してください"},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class OptionViewSet(viewsets.ModelViewSet):
    queryset = Option.objects.order_by("id")
    serializer_class = OptionSerializer

    def get_queryset(self):
        store = get_user_store(self.request)
        return super().get_queryset().filter(store=store)

    def perform_create(self, serializer):
        serializer.save(store=get_user_store(self.request))

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            self.perform_destroy(instance)
        except ProtectedError:
            return Response(
                {"detail": "このオプションは予約で使用されているため削除できません"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class RoomViewSet(viewsets.ModelViewSet):
    queryset = Room.objects.order_by("sort_order")
    serializer_class = RoomSerializer

    def get_queryset(self):
        store = get_user_store(self.request)
        return super().get_queryset().filter(store=store)

    def perform_create(self, serializer):
        serializer.save(store=get_user_store(self.request))

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            self.perform_destroy(instance)
        except ProtectedError:
            return Response(
                {"detail": "このルームは予約やシフトで使用されているため削除できません"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ExtensionViewSet(viewsets.ModelViewSet):
    queryset = Extension.objects.order_by("sort_order", "id")
    serializer_class = ExtensionSerializer

    def get_queryset(self):
        store = get_user_store(self.request)
        return super().get_queryset().filter(store=store)

    def perform_create(self, serializer):
        serializer.save(store=get_user_store(self.request))

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            self.perform_destroy(instance)
        except ProtectedError:
            return Response(
                {"detail": "この延長は使用されているため削除できません"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class NominationFeeViewSet(viewsets.ModelViewSet):
    queryset = NominationFee.objects.order_by("sort_order", "id")
    serializer_class = NominationFeeSerializer

    def get_queryset(self):
        store = get_user_store(self.request)
        return super().get_queryset().filter(store=store)

    def perform_create(self, serializer):
        serializer.save(store=get_user_store(self.request))

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            self.perform_destroy(instance)
        except ProtectedError:
            return Response(
                {"detail": "この指名料は使用されているため削除できません"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class DiscountViewSet(viewsets.ModelViewSet):
    queryset = Discount.objects.order_by("sort_order", "id")
    serializer_class = DiscountSerializer

    def get_queryset(self):
        store = get_user_store(self.request)
        return super().get_queryset().filter(store=store)

    def perform_create(self, serializer):
        serializer.save(store=get_user_store(self.request))

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            self.perform_destroy(instance)
        except ProtectedError:
            return Response(
                {"detail": "この割引は使用されているため削除できません"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class MediumViewSet(viewsets.ModelViewSet):
    queryset = Medium.objects.order_by("sort_order", "id")
    serializer_class = MediumSerializer

    def get_queryset(self):
        store = get_user_store(self.request)
        return super().get_queryset().filter(store=store)

    def perform_create(self, serializer):
        serializer.save(store=get_user_store(self.request))

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            self.perform_destroy(instance)
        except ProtectedError:
            return Response(
                {"detail": "この媒体は使用されているため削除できません"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


# ──────────────────────────────────────
# CastExpense — manager only
# ──────────────────────────────────────

class CastExpenseViewSet(viewsets.ModelViewSet):
    """雑費（キャスト控除）の CRUD — manager のみ"""
    queryset = CastExpense.objects.select_related("cast").order_by("-date", "cast", "id")
    serializer_class = CastExpenseSerializer
    filterset_fields = {
        "date": ["exact", "gte", "lte"],
        "cast": ["exact"],
    }
    ordering_fields = ["date", "cast"]
    ordering = ["-date", "cast"]

    def get_queryset(self):
        store = get_user_store(self.request)
        return super().get_queryset().filter(store=store)

    def check_manager(self, request):
        profile = getattr(request.user, "profile", None)
        if profile is None or profile.role != "manager":
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("この操作はマネージャーのみ利用可能です")

    def create(self, request, *args, **kwargs):
        self.check_manager(request)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self.check_manager(request)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self.check_manager(request)
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self.check_manager(request)
        return super().destroy(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(store=get_user_store(self.request))


# ──────────────────────────────────────
# CastExpenseTemplate — manager only（固定雑費テンプレ）
# ──────────────────────────────────────

class CastExpenseTemplateViewSet(viewsets.ModelViewSet):
    """キャスト別固定雑費テンプレの CRUD — manager のみ。削除は不可（is_activeで無効化）"""
    http_method_names = ["get", "post", "patch", "head", "options"]
    queryset = CastExpenseTemplate.objects.select_related("cast").order_by("cast", "-is_active", "id")
    serializer_class = CastExpenseTemplateSerializer
    filterset_fields = {
        "cast": ["exact"],
        "is_active": ["exact"],
    }

    def get_queryset(self):
        store = get_user_store(self.request)
        return super().get_queryset().filter(store=store)

    def check_manager(self, request):
        profile = getattr(request.user, "profile", None)
        if profile is None or profile.role != "manager":
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("この操作はマネージャーのみ利用可能です")

    def create(self, request, *args, **kwargs):
        self.check_manager(request)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self.check_manager(request)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self.check_manager(request)
        return super().partial_update(request, *args, **kwargs)

    def perform_create(self, serializer):
        instance = serializer.save(store=get_user_store(self.request))
        CastExpenseTemplateHistory.objects.create(
            template=instance, cast=instance.cast,
            name=instance.name, amount=instance.amount, memo=instance.memo,
            is_active=instance.is_active,
            action=CastExpenseTemplateHistory.Action.CREATE,
            edited_by=self.request.user,
        )

    def perform_update(self, serializer):
        previous_is_active = serializer.instance.is_active
        instance = serializer.save()
        if "is_active" in serializer.validated_data and instance.is_active != previous_is_active:
            action = (
                CastExpenseTemplateHistory.Action.ACTIVATE
                if instance.is_active
                else CastExpenseTemplateHistory.Action.DEACTIVATE
            )
        else:
            action = CastExpenseTemplateHistory.Action.UPDATE
        CastExpenseTemplateHistory.objects.create(
            template=instance, cast=instance.cast,
            name=instance.name, amount=instance.amount, memo=instance.memo,
            is_active=instance.is_active,
            action=action,
            edited_by=self.request.user,
        )


class CastExpenseTemplateHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """固定雑費テンプレ履歴の閲覧 — manager のみ"""
    serializer_class = CastExpenseTemplateHistorySerializer
    queryset = CastExpenseTemplateHistory.objects.select_related("cast", "edited_by").order_by("-edited_at")
    filterset_fields = {
        "template": ["exact"],
        "cast": ["exact"],
    }

    def get_queryset(self):
        store = get_user_store(self.request)
        return super().get_queryset().filter(cast__store=store)

    def list(self, request, *args, **kwargs):
        self.check_manager(request)
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        self.check_manager(request)
        return super().retrieve(request, *args, **kwargs)

    def check_manager(self, request):
        profile = getattr(request.user, "profile", None)
        if profile is None or profile.role != "manager":
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("この操作はマネージャーのみ利用可能です")


# ──────────────────────────────────────
# CastDailyCheckout — manager only（退勤提出の閲覧/確認, Phase 3-A）
# ──────────────────────────────────────

class CastCheckoutViewSet(viewsets.ModelViewSet):
    """退勤提出一覧/詳細の閲覧 + manager_memo編集 + 確認/差戻し/未確認に戻す — manager のみ。
    提出自体はキャスト側 CastCheckoutView からのみ行う（create/delete はここでは提供しない）。"""
    http_method_names = ["get", "patch", "head", "options"]
    queryset = (
        CastDailyCheckout.objects
        .select_related("cast", "reviewed_by")
        .prefetch_related("expense_snapshots")
        .order_by("-date", "cast")
    )
    serializer_class = CastDailyCheckoutSerializer
    filterset_fields = {
        "date": ["exact", "gte", "lte"],
        "cast": ["exact"],
        "status": ["exact"],
    }

    def get_queryset(self):
        self.check_manager(self.request)
        store = get_user_store(self.request)
        return super().get_queryset().filter(store=store)

    def check_manager(self, request):
        profile = getattr(request.user, "profile", None)
        if profile is None or profile.role != "manager":
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("この操作はマネージャーのみ利用可能です")

    def partial_update(self, request, *args, **kwargs):
        # manager_memo以外はserializerのread_only_fieldsで書き込み不可
        self.check_manager(request)
        return super().partial_update(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        """確認済みにする"""
        self.check_manager(request)
        instance = self.get_object()
        memo = request.data.get("manager_memo")
        if memo is not None:
            instance.manager_memo = memo
        instance.status = CastDailyCheckout.Status.REVIEWED
        instance.reviewed_at = timezone.now()
        instance.reviewed_by = request.user
        instance.save(update_fields=["manager_memo", "status", "reviewed_at", "reviewed_by", "updated_at"])
        return Response(CastDailyCheckoutSerializer(instance).data)

    @action(detail=True, methods=["post"])
    def return_to_cast(self, request, pk=None):
        """差戻し（キャストが再提出できる状態に戻す）"""
        self.check_manager(request)
        instance = self.get_object()
        memo = request.data.get("manager_memo")
        if memo is not None:
            instance.manager_memo = memo
        instance.status = CastDailyCheckout.Status.RETURNED
        instance.reviewed_at = timezone.now()
        instance.reviewed_by = request.user
        instance.save(update_fields=["manager_memo", "status", "reviewed_at", "reviewed_by", "updated_at"])
        return Response(CastDailyCheckoutSerializer(instance).data)

    @action(detail=True, methods=["post"])
    def reset_to_submitted(self, request, pk=None):
        """確認済み/差戻しを未確認（提出済み）に戻す"""
        self.check_manager(request)
        instance = self.get_object()
        instance.status = CastDailyCheckout.Status.SUBMITTED
        instance.reviewed_at = None
        instance.reviewed_by = None
        instance.save(update_fields=["status", "reviewed_at", "reviewed_by", "updated_at"])
        return Response(CastDailyCheckoutSerializer(instance).data)

    @action(detail=False, methods=["get"])
    def export_csv(self, request):
        """GET /api/cast-checkouts/export_csv/?date=&cast=&status= — 一覧と同じ絞り込みでCSV出力（manager限定）"""
        self.check_manager(request)
        queryset = self.filter_queryset(self.get_queryset())

        output = io.StringIO()
        output.write("﻿")  # BOM
        writer = csv.writer(output)
        writer.writerow([
            "日付", "キャスト名", "ステータス", "DONE件数", "売上", "給与見込み",
            "実際の持ち帰り金額", "提出日時", "確認者", "確認日時", "manager_memo", "cast_memo",
        ])
        for c in queryset:
            writer.writerow([
                c.date.isoformat(),
                c.cast.name,
                c.get_status_display(),
                c.done_count,
                c.total_sales,
                c.estimated_pay,
                c.actual_take_home_amount,
                c.submitted_at.strftime("%Y-%m-%d %H:%M") if c.submitted_at else "",
                c.reviewed_by.username if c.reviewed_by else "",
                c.reviewed_at.strftime("%Y-%m-%d %H:%M") if c.reviewed_at else "",
                c.manager_memo,
                c.cast_memo,
            ])

        resp = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="cast_checkouts.csv"'
        return resp


# ──────────────────────────────────────
# CastAdjustment — 調整金台帳（Phase 3-E）
# manager: 自店舗の調整金 CRUD + 未解消/解消/無効化。
# cast: 自分の分のみ閲覧（作成/編集/解消/無効化は不可）。
# 給与確定・支払い処理・DailySettlementView・CastDailyCheckoutの給与計算には一切接続しない。
# ──────────────────────────────────────

class CastAdjustmentViewSet(viewsets.ModelViewSet):
    """調整金台帳の CRUD — manager のみ。削除は不可（無効化=VOIDで対応）。"""
    http_method_names = ["get", "post", "patch", "head", "options"]
    queryset = (
        CastAdjustment.objects
        .select_related("cast", "created_by", "resolved_by", "source_checkout", "source_order")
        .order_by("-date", "-created_at")
    )
    serializer_class = CastAdjustmentSerializer
    filterset_fields = {
        "date": ["exact", "gte", "lte"],
        "cast": ["exact"],
        "status": ["exact"],
    }
    ordering_fields = ["date", "cast"]
    ordering = ["-date", "-created_at"]

    def get_queryset(self):
        self.check_manager(self.request)
        store = get_user_store(self.request)
        return super().get_queryset().filter(store=store)

    def check_manager(self, request):
        profile = getattr(request.user, "profile", None)
        if profile is None or profile.role != "manager":
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("この操作はマネージャーのみ利用可能です")

    def create(self, request, *args, **kwargs):
        self.check_manager(request)
        return super().create(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self.check_manager(request)
        instance = self.get_object()
        # 未解消（OPEN）以外は、メモ以外の変更を認めない（解消/無効化後の履歴を保護するため）
        if instance.status != CastAdjustment.Status.OPEN:
            non_memo_fields = [f for f in request.data.keys() if f != "memo"]
            if non_memo_fields:
                return Response(
                    {"detail": "未解消（OPEN）のもののみメモ以外を編集できます"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        return super().partial_update(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(store=get_user_store(self.request), created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        """未解消(OPEN) → 解消済み(RESOLVED)。resolved_by/resolved_at/resolved_memoを記録する。"""
        self.check_manager(request)
        instance = self.get_object()
        if instance.status != CastAdjustment.Status.OPEN:
            return Response(
                {"detail": "未解消のもののみ解消済みにできます"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance.status = CastAdjustment.Status.RESOLVED
        instance.resolved_by = request.user
        instance.resolved_at = timezone.now()
        instance.resolved_memo = request.data.get("resolved_memo", "") or ""
        instance.save(update_fields=["status", "resolved_by", "resolved_at", "resolved_memo", "updated_at"])
        return Response(CastAdjustmentSerializer(instance).data)

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        """OPEN/RESOLVED → 無効化(VOID)。resolved_by/resolved_atは無効化した操作者/日時として記録する。"""
        self.check_manager(request)
        instance = self.get_object()
        if instance.status == CastAdjustment.Status.VOID:
            return Response(
                {"detail": "すでに無効化されています"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance.status = CastAdjustment.Status.VOID
        instance.resolved_by = request.user
        instance.resolved_at = timezone.now()
        memo = request.data.get("resolved_memo")
        if memo is not None:
            instance.resolved_memo = memo
        instance.save(update_fields=["status", "resolved_by", "resolved_at", "resolved_memo", "updated_at"])
        return Response(CastAdjustmentSerializer(instance).data)

    @action(detail=False, methods=["get"])
    def export_csv(self, request):
        """GET /api/cast-adjustments/export_csv/?date=&cast=&status= — 一覧と同じ絞り込みでCSV出力（manager限定）"""
        self.check_manager(request)
        queryset = self.filter_queryset(self.get_queryset())

        output = io.StringIO()
        output.write("﻿")  # BOM
        writer = csv.writer(output)
        writer.writerow([
            "日付", "キャスト名", "タイトル", "金額", "ステータス", "メモ",
            "作成者", "作成日時", "解消者", "解消日時", "解消メモ",
            "source_type", "source_checkout_id", "source_order_id",
        ])
        for a in queryset:
            writer.writerow([
                a.date.isoformat(),
                a.cast.name,
                a.title,
                a.amount,
                a.get_status_display(),
                a.memo,
                a.created_by.username if a.created_by else "",
                a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "",
                a.resolved_by.username if a.resolved_by else "",
                a.resolved_at.strftime("%Y-%m-%d %H:%M") if a.resolved_at else "",
                a.resolved_memo,
                a.source_type,
                a.source_checkout_id or "",
                a.source_order_id or "",
            ])

        resp = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="cast_adjustments.csv"'
        return resp


@document_object_api_view
class CastAdjustmentListView(APIView):
    """GET /api/cast/adjustments/ — cast本人の未解消調整金一覧+合計、解消済み履歴（直近分のみ）。
    Phase 3-E: 給与確定・支払い処理とは接続しない、閲覧専用（作成/編集/解消/無効化は不可）。"""

    def get(self, request):
        cast = getattr(request.user, "cast_profile", None)
        if cast is None:
            return Response(
                {"detail": "このユーザーにキャストが紐づいていません"},
                status=status.HTTP_403_FORBIDDEN,
            )

        from django.db.models import Sum

        qs = CastAdjustment.objects.filter(cast=cast).exclude(status=CastAdjustment.Status.VOID)
        open_qs = qs.filter(status=CastAdjustment.Status.OPEN).order_by("-date", "-created_at")
        resolved_qs = qs.filter(status=CastAdjustment.Status.RESOLVED).order_by("-resolved_at")[:20]

        open_total = open_qs.aggregate(total=Sum("amount"))["total"] or 0

        return Response({
            "open_total": open_total,
            "open": CastAdjustmentCastSerializer(open_qs, many=True).data,
            "resolved_recent": CastAdjustmentCastSerializer(resolved_qs, many=True).data,
        })


# ──────────────────────────────────────
# CastNote — ノート/施術マニュアル（Phase 4）
# 店舗がキャスト向けに出す施術マニュアル/接客メモ/店舗ルール/連絡事項/お知らせ記事。
# 既存のRoomink操作マニュアル機能（フロントエンド静的データ manualData.js）とは別物で、互いに影響しない。
# manager: 自店舗の記事 CRUD + 公開/下書き/アーカイブ + ピン留め。cast: 公開済み・自分向け可視性の記事のみ閲覧。
# ──────────────────────────────────────

class CastNoteViewSet(viewsets.ModelViewSet):
    """ノート/施術マニュアルの CRUD — manager のみ。"""
    queryset = CastNote.objects.all().order_by("-is_pinned", "-published_at", "-created_at")
    serializer_class = CastNoteSerializer
    filterset_fields = {
        "status": ["exact"],
        "category": ["exact"],
        "is_pinned": ["exact"],
        "visibility": ["exact"],
    }
    search_fields = ["title", "body"]
    ordering = ["-is_pinned", "-published_at", "-created_at"]

    def get_queryset(self):
        self.check_manager(self.request)
        store = get_user_store(self.request)
        return super().get_queryset().filter(store=store)

    def check_manager(self, request):
        profile = getattr(request.user, "profile", None)
        if profile is None or profile.role != "manager":
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("この操作はマネージャーのみ利用可能です")

    def create(self, request, *args, **kwargs):
        self.check_manager(request)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        instance = serializer.save(
            store=get_user_store(self.request),
            created_by=self.request.user,
            updated_by=self.request.user,
        )
        if instance.status == CastNote.Status.PUBLISHED and instance.published_at is None:
            instance.published_at = timezone.now()
            instance.save(update_fields=["published_at"])

    def partial_update(self, request, *args, **kwargs):
        self.check_manager(request)
        return super().partial_update(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self.check_manager(request)
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        instance = serializer.save(updated_by=self.request.user)
        if instance.status == CastNote.Status.PUBLISHED and instance.published_at is None:
            instance.published_at = timezone.now()
            instance.save(update_fields=["published_at"])

    def destroy(self, request, *args, **kwargs):
        self.check_manager(request)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        """下書き/アーカイブ → 公開"""
        self.check_manager(request)
        instance = self.get_object()
        instance.status = CastNote.Status.PUBLISHED
        if instance.published_at is None:
            instance.published_at = timezone.now()
        instance.updated_by = request.user
        instance.save(update_fields=["status", "published_at", "updated_by", "updated_at"])
        return Response(CastNoteSerializer(instance).data)

    @action(detail=True, methods=["post"])
    def unpublish(self, request, pk=None):
        """公開 → 下書きに戻す"""
        self.check_manager(request)
        instance = self.get_object()
        instance.status = CastNote.Status.DRAFT
        instance.updated_by = request.user
        instance.save(update_fields=["status", "updated_by", "updated_at"])
        return Response(CastNoteSerializer(instance).data)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        """アーカイブへ移動"""
        self.check_manager(request)
        instance = self.get_object()
        instance.status = CastNote.Status.ARCHIVED
        instance.updated_by = request.user
        instance.save(update_fields=["status", "updated_by", "updated_at"])
        return Response(CastNoteSerializer(instance).data)

    @action(detail=True, methods=["post"])
    def pin(self, request, pk=None):
        self.check_manager(request)
        instance = self.get_object()
        instance.is_pinned = True
        instance.updated_by = request.user
        instance.save(update_fields=["is_pinned", "updated_by", "updated_at"])
        return Response(CastNoteSerializer(instance).data)

    @action(detail=True, methods=["post"])
    def unpin(self, request, pk=None):
        self.check_manager(request)
        instance = self.get_object()
        instance.is_pinned = False
        instance.updated_by = request.user
        instance.save(update_fields=["is_pinned", "updated_by", "updated_at"])
        return Response(CastNoteSerializer(instance).data)


@document_object_api_view
class CastNoteListView(APIView):
    """GET /api/cast/notes/ — cast本人がマイページから閲覧するノート一覧（公開済み・自分向け可視性のみ）。
    まずは一覧+本文同梱（フロント側でモーダル詳細表示する想定）。既読管理・コメント機能は今回対象外。"""

    def get(self, request):
        cast = getattr(request.user, "cast_profile", None)
        if cast is None:
            return Response(
                {"detail": "このユーザーにキャストが紐づいていません"},
                status=status.HTTP_403_FORBIDDEN,
            )

        qs = CastNote.objects.filter(
            store=cast.store,
            status=CastNote.Status.PUBLISHED,
            visibility__in=[CastNote.Visibility.CAST, CastNote.Visibility.ALL],
        ).order_by("-is_pinned", "-published_at", "-created_at")

        category = request.query_params.get("category")
        if category:
            qs = qs.filter(category=category)

        categories = sorted({c for c in qs.exclude(category="").values_list("category", flat=True)})

        pinned = qs.filter(is_pinned=True)
        recent = qs.filter(is_pinned=False)[:50]

        return Response({
            "categories": categories,
            "pinned": CastNoteCastSerializer(pinned, many=True).data,
            "recent": CastNoteCastSerializer(recent, many=True).data,
        })


# ──────────────────────────────────────
# ShiftAssignment — 出勤確認アラート土台（Phase 3-F）
# 通知送信は行わない。DB変更なし（confirmed_at + 現在時刻から都度判定）。
# ──────────────────────────────────────

@document_object_api_view
class ShiftConfirmAlertsView(APIView):
    """GET /api/op/shift-confirm-alerts/ — 本日以降の未確認シフトのうち、開始2時間前を切ったものをアラートとして返す。
    manager/staff共通（ShiftList.vueと同じ店舗スコープ）。LINE/SMS/メール等の外部送信は一切行わない。
    Phase 4: 各アラートに通知ログの有無/最終状態を付与する（土台のみ。実送信は行わない）。"""

    def get(self, request):
        store = get_user_store(request)
        now = timezone.now()
        today = timezone.localdate()
        tz = timezone.get_current_timezone()

        shifts = (
            ShiftAssignment.objects
            .filter(store=store, date__gte=today, confirmed_at__isnull=True, is_absent=False)
            .select_related("cast", "room")
            .order_by("date", "start_time")
        )

        shift_ids = [s.id for s in shifts]
        latest_logs = {}
        if shift_ids:
            for log in (
                ShiftConfirmNotificationLog.objects
                .filter(shift_assignment_id__in=shift_ids)
                .order_by("shift_assignment_id", "-created_at")
            ):
                key = (log.shift_assignment_id, log.alert_level)
                if key not in latest_logs:
                    latest_logs[key] = log

        alerts = []
        for s in shifts:
            start_dt = timezone.make_aware(datetime.combine(s.date, s.start_time), tz)
            minutes_until_start = int((start_dt - now).total_seconds() // 60)
            if minutes_until_start > 120:
                continue  # 2時間より前は対象外
            alert_level = "ONE_HOUR" if minutes_until_start <= 60 else "TWO_HOURS"
            last_log = latest_logs.get((s.id, alert_level))
            alerts.append({
                "shift_id": s.id,
                "cast_name": s.cast.name,
                "date": s.date.isoformat(),
                "start_time": str(s.start_time)[:5],
                "room_name": s.room.name if s.room_id else None,
                "confirmed_at": s.confirmed_at,
                "minutes_until_start": minutes_until_start,
                "alert_level": alert_level,
                "has_notification_log": last_log is not None,
                "last_notification_status": last_log.status if last_log else None,
                "last_notification_channel": last_log.channel if last_log else None,
                "last_notification_at": last_log.created_at if last_log else None,
                "external_send_supported": False,
            })

        return Response({"alerts": alerts, "external_send_supported": False})


@document_object_api_view
class ShiftConfirmNotificationTestView(APIView):
    """POST /api/op/shift-confirm-alerts/{shift_id}/mark_notification_test/
    出勤確認アラートの外部通知の土台（Phase 4）。実送信は行わず、
    「送信予定/送った扱い」のテストログ（ShiftConfirmNotificationLog）を1件作成するだけ。
    LINE/SMS/メール等の外部API呼び出しは一切行わない。manager のみ実行可能。"""

    def post(self, request, shift_id):
        _require_manager(request)
        store = get_user_store(request)

        shift = ShiftAssignment.objects.select_related("cast").filter(pk=shift_id, store=store).first()
        if shift is None:
            return Response(
                {"detail": "対象のシフトが見つかりません"},
                status=status.HTTP_404_NOT_FOUND,
            )

        alert_level = request.data.get("alert_level") or "TWO_HOURS"
        if alert_level not in ShiftConfirmNotificationLog.AlertLevel.values:
            return Response(
                {"detail": "alert_level は TWO_HOURS または ONE_HOUR を指定してください"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        target_type = request.data.get("target_type") or ShiftConfirmNotificationLog.TargetType.CAST
        if target_type not in ShiftConfirmNotificationLog.TargetType.values:
            target_type = ShiftConfirmNotificationLog.TargetType.CAST

        message = (
            f"[テストログ] {shift.cast.name} {shift.date.isoformat()} "
            f"{str(shift.start_time)[:5]} 出勤確認アラート（{alert_level}）"
        )
        log = ShiftConfirmNotificationLog.objects.create(
            store=store,
            shift_assignment=shift,
            cast=shift.cast,
            alert_level=alert_level,
            target_type=target_type,
            channel=ShiftConfirmNotificationLog.Channel.NONE,
            status=ShiftConfirmNotificationLog.Status.SKIPPED,
            message=message,
            error_message="実送信は現在無効化されています（テストログのみ。LINE/SMS/メール等の外部送信は行っていません）。",
            sent_at=None,
            created_by=request.user,
        )
        return Response(ShiftConfirmNotificationLogSerializer(log).data, status=status.HTTP_201_CREATED)


class ShiftConfirmNotificationLogViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/shift-confirm-notification-logs/ — 出勤確認外部通知ログの閲覧（manager/staff共通、自店舗のみ）。
    実送信は行わない土台のため、作成はShiftConfirmNotificationTestView経由のテストログ作成のみ。"""
    serializer_class = ShiftConfirmNotificationLogSerializer
    queryset = ShiftConfirmNotificationLog.objects.select_related("cast", "shift_assignment", "created_by").order_by("-created_at")
    filterset_fields = {
        "shift_assignment": ["exact"],
        "cast": ["exact"],
        "alert_level": ["exact"],
        "status": ["exact"],
    }

    def get_queryset(self):
        store = get_user_store(self.request)
        return super().get_queryset().filter(store=store)


# ──────────────────────────────────────
# PointLog — manager only
# ──────────────────────────────────────

class PointLogViewSet(viewsets.ModelViewSet):
    """ポイント記録の CRUD — manager のみ"""
    queryset = PointLog.objects.select_related("cast", "created_by").order_by("-date", "-created_at")
    serializer_class = PointLogSerializer
    filterset_fields = {
        "date": ["exact", "gte", "lte"],
        "cast": ["exact"],
    }
    ordering_fields = ["date", "cast"]
    ordering = ["-date", "-created_at"]

    def get_queryset(self):
        store = get_user_store(self.request)
        return super().get_queryset().filter(store=store)

    def check_manager(self, request):
        profile = getattr(request.user, "profile", None)
        if profile is None or profile.role != "manager":
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("この操作はマネージャーのみ利用可能です")

    def create(self, request, *args, **kwargs):
        self.check_manager(request)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self.check_manager(request)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self.check_manager(request)
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self.check_manager(request)
        return super().destroy(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(
            store=get_user_store(self.request),
            created_by=self.request.user,
        )


# ──────────────────────────────────────
# Cast Point Summary API
# ──────────────────────────────────────

@document_object_api_view
class CastPointSummaryView(APIView):
    """GET /api/cast/points/ — cast 本人のポイント累計 + 直近履歴"""

    def get(self, request):
        cast = getattr(request.user, "cast_profile", None)
        if cast is None:
            return Response(
                {"detail": "このユーザーにキャストが紐づいていません"},
                status=status.HTTP_403_FORBIDDEN,
            )

        from django.db.models import Sum

        total = PointLog.objects.filter(cast=cast).aggregate(
            total=Sum("points")
        )["total"] or 0

        recent = PointLog.objects.filter(cast=cast).order_by("-date", "-created_at")[:20]
        history = [
            {
                "id": p.id,
                "date": p.date.isoformat(),
                "points": p.points,
                "reason": p.reason,
            }
            for p in recent
        ]

        return Response({
            "total_points": total,
            "history": history,
        })


# ──────────────────────────────────────
# ShiftRequest — Cast API
# ──────────────────────────────────────

class CastShiftRequestViewSet(viewsets.ModelViewSet):
    serializer_class = CastShiftRequestSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = {
        "date": ["exact", "gte", "lte"],
        "status": ["exact"],
    }
    ordering = ["-created_at"]

    def get_queryset(self):
        cast = getattr(self.request.user, "cast_profile", None)
        if cast is None:
            return ShiftRequest.objects.none()
        return ShiftRequest.objects.filter(cast=cast).select_related("cast", "desired_room").order_by("-created_at")

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        cast = getattr(request.user, "cast_profile", None)
        if cast is None:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("このユーザーにキャストが紐づいていません")

    def perform_create(self, serializer):
        cast = self.request.user.cast_profile
        serializer.save(cast=cast, store=cast.store)

    def perform_update(self, serializer):
        if serializer.instance.status != ShiftRequest.Status.REQUESTED:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("申請中のもののみ編集できます")
        serializer.save()

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        obj = self.get_object()
        if obj.status != ShiftRequest.Status.REQUESTED:
            return Response(
                {"detail": "申請中のもののみ取消できます"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        obj.status = ShiftRequest.Status.CANCELLED
        obj.save(update_fields=["status", "updated_at"])
        return Response(CastShiftRequestSerializer(obj).data)


# ──────────────────────────────────────
# ShiftRequest — Operator API
# ──────────────────────────────────────

def _apply_shift_request_approval(
    obj,
    store,
    room,
    date,
    start_time,
    end_time,
    end_day_offset,
    admin_memo,
    user,
):
    """ShiftRequest承認の共通処理（ShiftAssignment作成 + ShiftRequestの承認内容/履歴保存）。
    OpShiftRequestViewSet.approve() と シフト申請CSV戻し承認(import_apply) の両方から呼ばれる。
    戻り値: (成功したか, エラーメッセージ or None)"""
    from .serializers import ShiftAssignmentSerializer

    sa_data = {
        "date": date,
        "cast": obj.cast_id,
        "room": room.id,
        "start_time": start_time,
        "end_time": end_time,
        "end_day_offset": end_day_offset,
    }
    sa_serializer = ShiftAssignmentSerializer(data=sa_data, context={"store": store})
    if not sa_serializer.is_valid():
        messages = []
        for field, errs in sa_serializer.errors.items():
            for e in errs:
                messages.append(str(e))
        return False, "; ".join(messages) or "シフト登録に失敗しました"
    shift = sa_serializer.save(store=store)

    obj.status = ShiftRequest.Status.APPROVED
    obj.admin_memo = admin_memo
    obj.approved_date = shift.date
    obj.approved_start_time = shift.start_time
    obj.approved_end_time = shift.end_time
    obj.approved_end_day_offset = shift.end_day_offset
    obj.approved_room = room
    obj.decided_at = timezone.now()
    obj.decided_by = user
    obj.save(update_fields=[
        "status", "admin_memo",
        "approved_date", "approved_start_time", "approved_end_time",
        "approved_end_day_offset", "approved_room",
        "decided_at", "decided_by", "updated_at",
    ])
    return True, None


SHIFT_REQUEST_CSV_HEADERS = [
    "shift_request_id", "cast_id", "cast_name",
    "requested_date", "requested_start_time", "requested_end_time",
    "requested_room_id", "requested_room_name",
    "approved_date", "approved_start_time", "approved_end_time",
    "approved_room_id", "approved_room_name",
    "status", "submitted_at", "admin_memo",
]

SHIFT_REQUEST_IMPORT_REQUIRED_COLUMNS = [
    "shift_request_id", "approved_date", "approved_start_time", "approved_end_time", "approved_room_id",
]


class OpShiftRequestViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OpShiftRequestSerializer
    queryset = ShiftRequest.objects.select_related("cast", "desired_room", "approved_room").order_by("-created_at")
    filterset_fields = {
        "date": ["exact", "gte", "lte"],
        "status": ["exact"],
        "cast": ["exact"],
    }
    ordering = ["-created_at"]

    def get_queryset(self):
        store = get_user_store(self.request)
        return super().get_queryset().filter(store=store)

    def check_manager(self, request):
        """CSVエクスポート/インポートはmanagerのみ（staff/castによる操作は非対象）。
        既存の approve/reject はこれまで通りstaff/managerともに利用可能（変更しない）。"""
        profile = getattr(request.user, "profile", None)
        if profile is None or profile.role != "manager":
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("この操作はマネージャーのみ利用可能です")

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        obj = self.get_object()
        store = get_user_store(request)
        if obj.status != ShiftRequest.Status.REQUESTED:
            return Response(
                {"detail": "申請中のもののみ承認できます"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        room_id = request.data.get("room")
        if not room_id:
            return Response(
                {"detail": "room は必須です"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            room = Room.objects.get(pk=room_id, store=store)
        except Room.DoesNotExist:
            return Response(
                {"detail": "指定された部屋が見つかりません"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        admin_memo = request.data.get("admin_memo", "")

        date = request.data.get("date") or obj.date
        start_time = request.data.get("start_time") or str(obj.start_time)
        end_time = request.data.get("end_time") or str(obj.end_time)
        end_day_offset = request.data.get("end_day_offset", obj.end_day_offset)

        ok, err = _apply_shift_request_approval(
            obj,
            store,
            room,
            date,
            start_time,
            end_time,
            end_day_offset,
            admin_memo,
            request.user,
        )
        if not ok:
            return Response({"detail": err}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OpShiftRequestSerializer(obj).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        obj = self.get_object()
        if obj.status != ShiftRequest.Status.REQUESTED:
            return Response(
                {"detail": "申請中のもののみ却下できます"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        admin_memo = request.data.get("admin_memo", "")
        obj.status = ShiftRequest.Status.REJECTED
        obj.admin_memo = admin_memo
        obj.decided_at = timezone.now()
        obj.decided_by = request.user
        obj.save(update_fields=["status", "admin_memo", "decided_at", "decided_by", "updated_at"])
        return Response(OpShiftRequestSerializer(obj).data)

    # ──────────────────────────────────────
    # シフト申請 CSV/Excel戻し承認の土台（v1: export → import(preview) → import(apply)）
    # 危険度が高いため、いきなり本承認まで自動実行しない。
    # apply は既存の approve() と同じ _apply_shift_request_approval() を再利用し、
    # 承認ロジック自体を重複実装しない。manager のみ利用可能。
    # ──────────────────────────────────────

    @action(detail=False, methods=["get"])
    def export_csv(self, request):
        """GET /api/op/shift-requests/export_csv/?date=&status=&cast= — 一覧と同じ絞り込みでCSV出力（manager限定）。
        Excelで編集する想定の列: approved_date/approved_start_time/approved_end_time/approved_room_id/admin_memo"""
        self.check_manager(request)
        queryset = self.filter_queryset(self.get_queryset())

        output = io.StringIO()
        output.write("﻿")  # BOM
        writer = csv.writer(output)
        writer.writerow(SHIFT_REQUEST_CSV_HEADERS)
        for r in queryset:
            writer.writerow([
                r.id, r.cast_id, r.cast.name,
                r.date.isoformat(), str(r.start_time)[:5],
                format_extended_time(r.end_time, r.end_day_offset),
                r.desired_room_id or "", r.desired_room.name if r.desired_room_id else "",
                r.approved_date.isoformat() if r.approved_date else "",
                str(r.approved_start_time)[:5] if r.approved_start_time else "",
                format_extended_time(
                    r.approved_end_time,
                    r.approved_end_day_offset,
                ) if r.approved_end_time else "",
                r.approved_room_id or "", r.approved_room.name if r.approved_room_id else "",
                r.status,
                r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
                r.admin_memo,
            ])

        resp = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="shift_requests.csv"'
        return resp

    def _validate_import_row(self, store, row, row_number):
        """CSV/戻し承認1行分の検証。DBは更新しない（preview/apply共通のバリデーションのみ）。"""
        from datetime import time as dt_time

        errors = []
        warnings = []

        raw_id = (row.get("shift_request_id") or "").strip()
        csv_data = {
            "approved_date": (row.get("approved_date") or "").strip(),
            "approved_start_time": (row.get("approved_start_time") or "").strip(),
            "approved_end_time": (row.get("approved_end_time") or "").strip(),
            "approved_room_id": (row.get("approved_room_id") or "").strip(),
            "approved_room_name": None,
            "admin_memo": row.get("admin_memo") or "",
        }

        if not raw_id.isdigit():
            errors.append("shift_request_id が不正です（数値を指定してください）")
            return {
                "row_number": row_number, "shift_request_id": raw_id or None,
                "original": None, "csv": csv_data, "errors": errors, "warnings": warnings,
                "can_apply": False,
            }

        obj = (
            ShiftRequest.objects
            .select_related("cast", "desired_room", "approved_room")
            .filter(pk=int(raw_id), store=store)
            .first()
        )
        if obj is None:
            errors.append("shift_request_id が見つかりません（自店舗の申請でない可能性があります）")
            return {
                "row_number": row_number, "shift_request_id": int(raw_id),
                "original": None, "csv": csv_data, "errors": errors, "warnings": warnings,
                "can_apply": False,
            }

        original = {
            "cast_id": obj.cast_id,
            "cast_name": obj.cast.name,
            "date": obj.date.isoformat(),
            "start_time": str(obj.start_time)[:5],
            "end_time": format_extended_time(obj.end_time, obj.end_day_offset),
            "desired_room_name": obj.desired_room.name if obj.desired_room_id else None,
            "status": obj.status,
            "status_display": obj.get_status_display(),
        }

        cast_id_col = (row.get("cast_id") or "").strip()
        if cast_id_col and cast_id_col.isdigit() and int(cast_id_col) != obj.cast_id:
            errors.append("cast_id がこの申請のキャストと一致しません")

        if obj.status != ShiftRequest.Status.REQUESTED:
            errors.append(f"申請中（REQUESTED）ではないため反映できません（現在: {obj.get_status_display()}）")

        approved_date = None
        if not csv_data["approved_date"]:
            errors.append("approved_date は必須です")
        else:
            try:
                approved_date = date_type.fromisoformat(csv_data["approved_date"])
            except ValueError:
                errors.append("approved_date の形式が不正です（YYYY-MM-DD）")

        def _parse_time(v):
            if not v:
                return None
            try:
                parts = v.split(":")
                return dt_time(int(parts[0]), int(parts[1]))
            except (ValueError, IndexError):
                return None

        start_t = _parse_time(csv_data["approved_start_time"])
        if not csv_data["approved_start_time"]:
            errors.append("approved_start_time は必須です")
        elif start_t is None:
            errors.append("approved_start_time の形式が不正です（HH:MM）")

        end_t = None
        end_day_offset = 0
        if not csv_data["approved_end_time"]:
            errors.append("approved_end_time は必須です")
        else:
            try:
                end_t, end_day_offset = parse_extended_time(
                    csv_data["approved_end_time"]
                )
            except BusinessDateTimeError as exc:
                errors.append(str(exc))

        approved_start = approved_end = None
        if approved_date and start_t and end_t:
            try:
                approved_start, approved_end = build_business_interval(
                    approved_date,
                    start_t,
                    end_t,
                    end_day_offset=end_day_offset,
                    timezone_name=store.timezone,
                )
            except BusinessDateTimeError as exc:
                errors.append(str(exc))

        room = None
        if not csv_data["approved_room_id"]:
            errors.append("approved_room_id は必須です")
        elif not csv_data["approved_room_id"].isdigit():
            errors.append("approved_room_id が不正です（数値を指定してください）")
        else:
            room = Room.objects.filter(pk=int(csv_data["approved_room_id"]), store=store).first()
            if room is None:
                errors.append("approved_room_id が自店舗の部屋として見つかりません")
        csv_data["approved_room_name"] = room.name if room else None

        if approved_start and approved_end:
            existing_shifts = ShiftAssignment.objects.filter(
                store=store,
                cast_id=obj.cast_id,
                date__range=(approved_date - timedelta(days=1), approved_date + timedelta(days=1)),
            )
            for existing in existing_shifts:
                try:
                    existing_start, existing_end = build_business_interval(
                        existing.date,
                        existing.start_time,
                        existing.end_time,
                        end_day_offset=existing.end_day_offset,
                        timezone_name=store.timezone,
                    )
                except BusinessDateTimeError:
                    continue
                if intervals_overlap(
                    approved_start,
                    approved_end,
                    existing_start,
                    existing_end,
                ):
                    warnings.append("同じキャストの既存シフトと時間帯が重複しています")
                    break

        return {
            "row_number": row_number,
            "shift_request_id": obj.id,
            "original": original,
            "csv": csv_data,
            "errors": errors,
            "warnings": warnings,
            "can_apply": len(errors) == 0,
        }

    @action(detail=False, methods=["post"])
    def import_preview(self, request):
        """POST /api/op/shift-requests/import_preview/ multipart file=<csv> — 反映せず検証結果のみ返す（manager限定）"""
        self.check_manager(request)
        store = get_user_store(request)

        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response({"detail": "file が必要です"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            text = file_obj.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            return Response(
                {"detail": "ファイルの文字コードが不正です（UTF-8で保存してください）"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reader = csv.DictReader(io.StringIO(text))
        fieldnames = reader.fieldnames or []
        missing = [h for h in SHIFT_REQUEST_IMPORT_REQUIRED_COLUMNS if h not in fieldnames]
        if missing:
            return Response(
                {"detail": f"必須列が不足しています: {', '.join(missing)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rows = []
        for i, row in enumerate(reader, start=2):  # 1行目はヘッダ
            if not any((row or {}).values()):
                continue
            rows.append(self._validate_import_row(store, row, i))

        applicable = sum(1 for r in rows if r["can_apply"])
        return Response({
            "total_rows": len(rows),
            "applicable_rows": applicable,
            "rows": rows,
        })

    @action(detail=False, methods=["post"])
    def import_apply(self, request):
        """POST /api/op/shift-requests/import_apply/ body: {"rows": [{shift_request_id, approved_date, ...}, ...]}
        manager が明示的に確認したもの（import_previewのレスポンスから選択した行）のみをサーバ側で再検証し、
        問題ない行だけ既存の承認ロジック（_apply_shift_request_approval）で反映する。manager限定。"""
        self.check_manager(request)
        store = get_user_store(request)

        rows = request.data.get("rows")
        if not isinstance(rows, list) or not rows:
            return Response(
                {"detail": "rows は必須です（反映する行の配列。import_previewの結果から選択してください）"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        results = []
        with transaction.atomic():
            for raw_row in rows:
                if not isinstance(raw_row, dict):
                    continue
                row_number = raw_row.get("row_number") or 0
                row_for_validation = {
                    "shift_request_id": raw_row.get("shift_request_id"),
                    "cast_id": raw_row.get("cast_id"),
                    "approved_date": raw_row.get("approved_date"),
                    "approved_start_time": raw_row.get("approved_start_time"),
                    "approved_end_time": raw_row.get("approved_end_time"),
                    "approved_room_id": raw_row.get("approved_room_id"),
                    "admin_memo": raw_row.get("admin_memo") or "",
                }
                # 文字列化（プレビュー時と同じ検証ロジックを再利用するため）
                row_for_validation = {k: ("" if v is None else str(v)) for k, v in row_for_validation.items()}

                validated = self._validate_import_row(store, row_for_validation, row_number)
                if not validated["can_apply"]:
                    results.append({**validated, "applied": False})
                    continue

                room = Room.objects.filter(pk=int(row_for_validation["approved_room_id"]), store=store).first()
                obj = ShiftRequest.objects.filter(pk=validated["shift_request_id"], store=store).first()
                if obj is None or obj.status != ShiftRequest.Status.REQUESTED or room is None:
                    validated["can_apply"] = False
                    validated["errors"].append("反映直前に状態が変わったため反映できませんでした（再度エクスポートしてご確認ください）")
                    results.append({**validated, "applied": False})
                    continue

                end_t, end_day_offset = parse_extended_time(
                    row_for_validation["approved_end_time"]
                )

                ok, err = _apply_shift_request_approval(
                    obj, store, room,
                    row_for_validation["approved_date"],
                    row_for_validation["approved_start_time"],
                    end_t,
                    end_day_offset,
                    row_for_validation["admin_memo"],
                    request.user,
                )
                if not ok:
                    validated["can_apply"] = False
                    validated["errors"].append(err)
                    results.append({**validated, "applied": False})
                else:
                    results.append({**validated, "applied": True})

        applied_count = sum(1 for r in results if r["applied"])
        return Response({
            "applied_count": applied_count,
            "total": len(results),
            "results": results,
        })



# ──────────────────────────────────────
# CSV Import  (2-stage: preview → execute)
# ──────────────────────────────────────

MODEL_MAP = {
    "room": Room,
    "cast": Cast,
    "course": Course,
    "option": Option,
    "customer": Customer,
}

REQUIRED_HEADERS = {
    "room": ["name"],
    "cast": ["name"],
    "course": ["name", "duration", "price"],
    "option": ["name", "price"],
    "customer": ["phone"],
}

OPTIONAL_HEADERS = {
    "room": ["sort_order"],
    "cast": ["avatar_url"],
    "course": [],
    "option": [],
    "customer": ["display_name", "flag", "memo"],
}


def _parse_csv(file_obj):
    """UTF-8 (BOM対応) で CSV を読み、行リストを返す"""
    text = file_obj.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader), reader.fieldnames or []


def _validate_headers(model_key, fieldnames):
    required = REQUIRED_HEADERS[model_key]
    missing = [h for h in required if h not in fieldnames]
    if missing:
        return f"必須ヘッダが不足: {', '.join(missing)}"
    return None


def _upsert_rows(store, model_key, rows):
    """upsert して (created, updated) のカウントを返す"""
    created = 0
    updated = 0

    for row in rows:
        # 空行スキップ
        if not any(row.values()):
            continue

        if model_key == "room":
            obj, is_new = Room.objects.update_or_create(
                store=store, name=row["name"],
                defaults={"sort_order": int(row.get("sort_order") or 0)},
            )
        elif model_key == "cast":
            obj, is_new = update_or_create_cast_with_user(
                store=store, name=row["name"],
                defaults={"avatar_url": row.get("avatar_url") or ""},
            )
        elif model_key == "course":
            obj, is_new = Course.objects.update_or_create(
                store=store, name=row["name"],
                defaults={
                    "duration": int(row["duration"]),
                    "price": int(row["price"]),
                },
            )
        elif model_key == "option":
            obj, is_new = Option.objects.update_or_create(
                store=store, name=row["name"],
                defaults={"price": int(row["price"])},
            )
        elif model_key == "customer":
            defaults = {}
            if row.get("display_name"):
                defaults["display_name"] = row["display_name"]
            if row.get("flag"):
                defaults["flag"] = row["flag"]
            if row.get("memo"):
                defaults["memo"] = row["memo"]
            obj, is_new = Customer.objects.update_or_create(
                store=store, phone=normalize_phone(row["phone"]),
                defaults=defaults,
            )

        if is_new:
            created += 1
        else:
            updated += 1

    return created, updated


@document_object_api_view
class CsvImportView(APIView):
    """
    POST /api/op/csv-import/?model=room
      - multipart/form-data  file=<csv>
      - query: model = room|cast|course|option|customer
      - query: preview = 1  → プレビューのみ（先頭10行）
    """
    parser_classes = [parsers.MultiPartParser]

    def post(self, request):
        model_key = request.query_params.get("model", "").lower()
        if model_key not in MODEL_MAP:
            return Response(
                {"detail": f"model は {', '.join(MODEL_MAP.keys())} のいずれかを指定してください"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response(
                {"detail": "file が必要です"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rows, fieldnames = _parse_csv(file_obj)

        header_err = _validate_headers(model_key, fieldnames)
        if header_err:
            return Response({"detail": header_err}, status=status.HTTP_400_BAD_REQUEST)

        is_preview = request.query_params.get("preview") == "1"

        if is_preview:
            return Response({
                "model": model_key,
                "total_rows": len(rows),
                "headers": fieldnames,
                "preview": rows[:10],
            })

        store = get_user_store(request)

        try:
            with transaction.atomic():
                created, updated = _upsert_rows(store, model_key, rows)
        except Exception as e:
            return Response(
                {"detail": f"インポートエラー: {e}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({
            "model": model_key,
            "total_rows": len(rows),
            "created": created,
            "updated": updated,
        })


# ──────────────────────────────────────
# CTI — Webhook / Queue
# ──────────────────────────────────────

def _is_valid_cti_token(token):
    configured_token = os.getenv("CTI_SHARED_TOKEN", "")
    if not configured_token.strip():
        return False
    return secrets.compare_digest(str(token or ""), configured_token)


@document_object_api_view
class CtiInboundView(APIView):
    """
    POST /api/op/cti/inbound/
    CTI Webhook: 着信通知を受けて CallLog を作成/更新する。
    認証: X-CTI-TOKEN ヘッダーのみ。SessionAuth/CSRF は無効化。
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        token = request.META.get("HTTP_X_CTI_TOKEN", "")
        if not _is_valid_cti_token(token):
            return Response({"detail": "無効なトークンです"}, status=status.HTTP_403_FORBIDDEN)

        contact_id = request.data.get("contact_id")
        raw_from = request.data.get("from_phone", "")
        raw_to = request.data.get("to_phone", "")

        if not contact_id or not raw_from or not raw_to:
            return Response(
                {"detail": "contact_id, from_phone, to_phone は必須です"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from_phone = normalize_phone(raw_from)
        to_phone = normalize_phone(raw_to)

        # to_phone → StorePhoneNumber で store 特定
        try:
            store_phone = StorePhoneNumber.objects.select_related("store").get(phone=to_phone, is_active=True)
        except StorePhoneNumber.DoesNotExist:
            return Response(
                {"detail": f"着信先番号 {to_phone} に対応する店舗が見つかりません"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        store = store_phone.store

        # from_phone → Customer 検索
        customer = Customer.objects.filter(store=store, phone=from_phone).first()

        # is_repeat: 同一 store + from_phone で直近 10 分以内の CallLog
        threshold = timezone.now() - timedelta(minutes=10)
        is_repeat = CallLog.objects.filter(
            store=store, from_phone=from_phone, created_at__gte=threshold,
        ).exclude(contact_id=contact_id).exists()

        # CallLog upsert
        call, created = CallLog.objects.update_or_create(
            contact_id=contact_id,
            defaults={
                "store": store,
                "from_phone": from_phone,
                "to_phone": to_phone,
                "customer": customer,
                "is_repeat": is_repeat,
            },
        )
        # 初回のみ status=NEW（既存は上書きしない）
        if created:
            call.status = CallLog.Status.NEW
            call.save(update_fields=["status"])

        return Response({
            "id": call.id,
            "contact_id": call.contact_id,
            "store_id": store.id,
            "store_name": store.name,
            "from_phone": call.from_phone,
            "customer_id": call.customer_id,
            "customer_name": str(customer) if customer else None,
            "is_repeat": call.is_repeat,
            "status": call.status,
            "created": created,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@document_object_api_view
class CtiQueueView(APIView):
    """GET /api/op/cti/queue/ — 未対応 / 対応中コール一覧"""

    def get(self, request):
        store = get_user_store(request)
        calls = (
            CallLog.objects
            .filter(store=store, status__in=[CallLog.Status.NEW, CallLog.Status.IN_PROGRESS])
            .select_related("store", "customer", "assigned_to")
            .order_by("-created_at")
        )
        data = []
        for c in calls:
            data.append({
                "id": c.id,
                "contact_id": c.contact_id,
                "store_id": c.store_id,
                "store_name": c.store.name,
                "from_phone": c.from_phone,
                "to_phone": c.to_phone,
                "customer_id": c.customer_id,
                "customer_name": str(c.customer) if c.customer else None,
                "is_repeat": c.is_repeat,
                "status": c.status,
                "assigned_to": c.assigned_to.username if c.assigned_to else None,
                "created_at": c.created_at,
                "updated_at": c.updated_at,
            })
        return Response({"calls": data})


@document_object_api_view
class CtiCallStartView(APIView):
    """POST /api/op/cti/calls/{id}/start/ — 対応開始"""

    def post(self, request, pk):
        try:
            call = CallLog.objects.get(pk=pk)
        except CallLog.DoesNotExist:
            return Response({"detail": "コールが見つかりません"}, status=status.HTTP_404_NOT_FOUND)

        if call.status not in (CallLog.Status.NEW, CallLog.Status.IN_PROGRESS):
            return Response(
                {"detail": f"ステータスが {call.get_status_display()} のため開始できません"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        call.status = CallLog.Status.IN_PROGRESS
        call.assigned_to = request.user
        call.save(update_fields=["status", "assigned_to", "updated_at"])
        return Response({"id": call.id, "status": call.status})


@document_object_api_view
class CtiCallDoneView(APIView):
    """POST /api/op/cti/calls/{id}/done/ — 対応完了"""

    def post(self, request, pk):
        try:
            call = CallLog.objects.get(pk=pk)
        except CallLog.DoesNotExist:
            return Response({"detail": "コールが見つかりません"}, status=status.HTTP_404_NOT_FOUND)

        if call.status in (CallLog.Status.DONE, CallLog.Status.MISSED):
            return Response(
                {"detail": f"ステータスが {call.get_status_display()} のため完了にできません"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        call.status = CallLog.Status.DONE
        call.save(update_fields=["status", "updated_at"])
        return Response({"id": call.id, "status": call.status})


@document_object_api_view
class CtiCallNoteView(APIView):
    """POST /api/op/cti/calls/{id}/notes/ — メモ追加"""

    def post(self, request, pk):
        try:
            call = CallLog.objects.get(pk=pk)
        except CallLog.DoesNotExist:
            return Response({"detail": "コールが見つかりません"}, status=status.HTTP_404_NOT_FOUND)

        body = (request.data.get("body") or "").strip()
        if not body:
            return Response(
                {"detail": "body は必須です"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        note = CallNote.objects.create(call=call, author=request.user, body=body)
        return Response({
            "id": note.id,
            "call_id": call.id,
            "author": request.user.username,
            "body": note.body,
            "created_at": note.created_at,
        }, status=status.HTTP_201_CREATED)


# ──────────────────────────────────────
# CallLog op manual API (Phase 3-A)
# 既存 CTI/Webhook 系 View とは別に、運営画面用の手動架電履歴 API を提供する。
# ──────────────────────────────────────

class CallLogViewSet(viewsets.ModelViewSet):
    """
    /api/op/call-logs/ — 運営画面用 手動架電履歴。
    既存 CtiInboundView / CtiCallNoteView 等とは認証思想が異なるため別 ViewSet として独立させる。
    """
    queryset = CallLog.objects.all()
    serializer_class = CallLogSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        store = get_user_store(self.request)
        qs = (
            CallLog.objects
            .filter(store=store)
            .select_related("customer", "assigned_to")
            .prefetch_related("notes", "notes__author")
            .order_by("-created_at")
        )

        customer_id = self.request.query_params.get("customer")
        if customer_id:
            try:
                qs = qs.filter(customer_id=int(customer_id))
            except (TypeError, ValueError):
                qs = qs.none()

        phone = self.request.query_params.get("phone")
        if phone:
            normalized = normalize_phone(phone)
            if normalized:
                qs = qs.filter(from_phone=normalized)
            else:
                qs = qs.none()

        return qs

    def create(self, request, *args, **kwargs):
        store = get_user_store(request)
        from_phone_raw = request.data.get("from_phone") or ""
        from_phone = normalize_phone(from_phone_raw)
        if not from_phone:
            return Response(
                {"detail": "from_phone は必須です"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        customer = None
        customer_id = request.data.get("customer")
        if customer_id not in (None, "", 0):
            try:
                customer = Customer.objects.get(pk=int(customer_id), store=store)
            except (Customer.DoesNotExist, TypeError, ValueError):
                return Response(
                    {"detail": "customer が不正です（同一店舗の顧客を指定してください）"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        note_body = (request.data.get("note_body") or "").strip()

        with transaction.atomic():
            call = CallLog.objects.create(
                store=store,
                contact_id=f"manual-{uuid.uuid4().hex}",
                from_phone=from_phone,
                to_phone="",
                status=CallLog.Status.DONE,
                assigned_to=request.user,
                customer=customer,
                is_repeat=False,
            )
            if note_body:
                CallNote.objects.create(call=call, author=request.user, body=note_body)

        call = (
            CallLog.objects
            .select_related("customer", "assigned_to")
            .prefetch_related("notes", "notes__author")
            .get(pk=call.pk)
        )
        return Response(
            CallLogSerializer(call).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="add-note")
    def add_note(self, request, pk=None):
        store = get_user_store(request)
        try:
            call = CallLog.objects.get(pk=pk, store=store)
        except CallLog.DoesNotExist:
            return Response(
                {"detail": "コールが見つかりません"},
                status=status.HTTP_404_NOT_FOUND,
            )

        body = (request.data.get("body") or "").strip()
        if not body:
            return Response(
                {"detail": "body は必須です"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        note = CallNote.objects.create(call=call, author=request.user, body=body)
        return Response(
            CallNoteSerializer(note).data,
            status=status.HTTP_201_CREATED,
        )


# ──────────────────────────────────────
# Twilio Webhook
# ──────────────────────────────────────

def _mask_phone(phone):
    digits = "".join(char for char in str(phone or "") if char.isdigit())
    return f"***{digits[-4:]}" if digits else "***"


def _twilio_validation_url(request):
    public_base_url = settings.TWILIO_WEBHOOK_PUBLIC_BASE_URL
    if public_base_url:
        return f"{public_base_url}{request.get_full_path()}"
    return request.build_absolute_uri()


def _is_valid_twilio_request(request):
    allow_unsigned = (
        settings.TWILIO_WEBHOOK_ALLOW_UNSIGNED
        and settings.DEBUG
        and "DYNO" not in os.environ
    )
    if allow_unsigned:
        logger.warning("Twilio webhook signature validation is explicitly disabled")
        return True

    auth_token = settings.TWILIO_AUTH_TOKEN
    signature = request.headers.get("X-Twilio-Signature", "")
    if not auth_token:
        logger.error("Twilio webhook rejected: Auth Token is not configured")
        return False
    if not signature:
        logger.warning("Twilio webhook rejected: missing signature")
        return False

    try:
        is_valid = RequestValidator(auth_token).validate(
            _twilio_validation_url(request),
            request.POST,
            signature,
        )
    except Exception:
        logger.warning("Twilio webhook rejected: signature validation failed")
        return False
    if not is_valid:
        logger.warning("Twilio webhook rejected: invalid signature")
    return is_valid


def _twilio_forbidden_response():
    return HttpResponse("Forbidden", content_type="text/plain", status=403)


@extend_schema(operation_id="twilio_voice_webhook", request=OpenApiTypes.OBJECT, responses=OpenApiTypes.STR)
@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def twilio_voice_webhook(request):
    """
    POST /api/webhook/twilio/voice/
    Twilio Voice webhook: 着信時に呼ばれる。
    form-encoded で From, To, CallSid, CallStatus が届く。
    既存 CTI ロジックで CallLog を作成し、TwiML を返す。
    """
    if not _is_valid_twilio_request(request):
        return _twilio_forbidden_response()

    call_sid = request.data.get("CallSid", "")
    raw_from = request.data.get("From", "")
    raw_to = request.data.get("To", "")
    call_status = request.data.get("CallStatus", "")

    logger.info(
        "Twilio voice webhook: CallSid=%s From=%s To=%s Status=%s",
        call_sid, _mask_phone(raw_from), _mask_phone(raw_to), call_status,
    )

    if not call_sid or not raw_from or not raw_to:
        logger.warning("Twilio voice webhook: missing required fields")
        return HttpResponse(
            '<?xml version="1.0" encoding="UTF-8"?><Response><Say language="ja-JP">エラーが発生しました</Say></Response>',
            content_type="application/xml",
            status=400,
        )

    from_phone = normalize_phone(raw_from)
    to_phone = normalize_phone(raw_to)
    logger.info(
        "Twilio voice: normalized from=%s to=%s",
        _mask_phone(from_phone), _mask_phone(to_phone),
    )

    # to_phone → StorePhoneNumber で store 特定
    store_phone = StorePhoneNumber.objects.select_related("store").filter(phone=to_phone, is_active=True).first()
    if not store_phone:
        logger.warning(
            "Twilio voice: StorePhoneNumber not found for to=%s",
            _mask_phone(to_phone),
        )
        return HttpResponse(
            '<?xml version="1.0" encoding="UTF-8"?><Response><Say language="ja-JP">この番号は登録されていません</Say></Response>',
            content_type="application/xml",
        )

    store = store_phone.store

    # from_phone → Customer 検索
    customer = Customer.objects.filter(store=store, phone=from_phone).first()

    # is_repeat: 同一 store + from_phone で直近 10 分以内
    threshold = timezone.now() - timedelta(minutes=10)
    is_repeat = CallLog.objects.filter(
        store=store, from_phone=from_phone, created_at__gte=threshold,
    ).exclude(contact_id=call_sid).exists()

    # CallLog upsert
    call, created = CallLog.objects.update_or_create(
        contact_id=call_sid,
        defaults={
            "store": store,
            "from_phone": from_phone,
            "to_phone": to_phone,
            "customer": customer,
            "is_repeat": is_repeat,
        },
    )
    if created:
        call.status = CallLog.Status.NEW
        call.save(update_fields=["status"])

    # TwiML レスポンス（受付メッセージ + StatusCallback）
    customer_name = customer.display_name if customer and customer.display_name else ""
    if customer_name:
        say_text = f"お電話ありがとうございます。{customer_name}様ですね。少々お待ちください。"
    else:
        say_text = "お電話ありがとうございます。少々お待ちください。"

    # StatusCallback URL を構築
    status_url = os.getenv("TWILIO_STATUS_CALLBACK_URL", "")
    status_attr = f' statusCallback="{status_url}" statusCallbackMethod="POST"' if status_url else ""

    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response{status_attr}>"
        f'<Say language="ja-JP">{say_text}</Say>'
        "</Response>"
    )
    return HttpResponse(twiml, content_type="application/xml")


@extend_schema(operation_id="twilio_status_webhook", request=OpenApiTypes.OBJECT, responses=OpenApiTypes.STR)
@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def twilio_status_webhook(request):
    """
    POST /api/webhook/twilio/status/
    Twilio StatusCallback: 通話ステータス変更時に呼ばれる。
    completed / no-answer / busy / failed / canceled を CallLog に反映。
    """
    if not _is_valid_twilio_request(request):
        return _twilio_forbidden_response()

    call_sid = request.data.get("CallSid", "")
    call_status = request.data.get("CallStatus", "")
    raw_from = request.data.get("From", "")
    raw_to = request.data.get("To", "")

    logger.info(
        "Twilio status webhook: CallSid=%s Status=%s From=%s To=%s",
        call_sid, call_status, _mask_phone(raw_from), _mask_phone(raw_to),
    )

    if not call_sid:
        return HttpResponse("ok", content_type="text/plain")

    try:
        call = CallLog.objects.get(contact_id=call_sid)
    except CallLog.DoesNotExist:
        # Fallback: voice webhook で CallLog が作られなかった場合、ここで作成を試みる
        if raw_from and raw_to:
            from_phone = normalize_phone(raw_from)
            to_phone = normalize_phone(raw_to)
            store_phone = StorePhoneNumber.objects.select_related("store").filter(phone=to_phone, is_active=True).first()
            if store_phone:
                store = store_phone.store
                customer = Customer.objects.filter(store=store, phone=from_phone).first()
                call = CallLog.objects.create(
                    contact_id=call_sid,
                    store=store,
                    from_phone=from_phone,
                    to_phone=to_phone,
                    customer=customer,
                    status=CallLog.Status.NEW,
                )
                logger.info("Twilio status fallback: created CallLog#%s for %s", call.pk, call_sid)
            else:
                logger.warning(
                    "Twilio status fallback: StorePhoneNumber not found for to=%s",
                    _mask_phone(to_phone),
                )
                return HttpResponse("ok", content_type="text/plain")
        else:
            logger.warning("Twilio status webhook: CallLog not found for %s and no From/To for fallback", call_sid)
            return HttpResponse("ok", content_type="text/plain")

    # オペレーターが既に対応完了にしている場合は上書きしない
    if call.status in (CallLog.Status.DONE,):
        return HttpResponse("ok", content_type="text/plain")

    # Twilio ステータス → Roomink ステータスへのマッピング
    # 通話不成立(failed/busy/no-answer/canceled)のみ MISSED に遷移する。
    # completed は通話成立なので、NEW のまま画面パネルに残し、人間が対応完了するまで消さない。
    if call_status in ("no-answer", "busy", "failed", "canceled"):
        call.status = CallLog.Status.MISSED
        call.save(update_fields=["status", "updated_at"])

    return HttpResponse("ok", content_type="text/plain")


# ──────────────────────────────────────
# Sales
# ──────────────────────────────────────

def _parse_sales_range(request, store):
    """range / date_from / date_to パラメータを解析して (date_from, date_to) を返す。"""
    today = business_date_for_datetime(timezone.now(), store.timezone)
    range_key = request.query_params.get("range")

    if range_key == "today":
        return today, today
    elif range_key == "week":
        # 月曜始まり
        mon = today - timedelta(days=today.weekday())
        return mon, today
    elif range_key == "month":
        return today.replace(day=1), today
    else:
        df = request.query_params.get("date_from")
        dt = request.query_params.get("date_to")
        if not df or not dt:
            return None, None
        try:
            return date_type.fromisoformat(df), date_type.fromisoformat(dt)
        except ValueError:
            return None, None


def _require_manager(request):
    """manager でなければ PermissionDenied を返す。OK なら None。"""
    profile = getattr(request.user, "profile", None)
    if profile is None or profile.role != "manager":
        from rest_framework.exceptions import PermissionDenied
        raise PermissionDenied("この機能はマネージャーのみ利用できます。")


@document_object_api_view
class SalesSummaryView(APIView):
    """GET /api/op/sales-summary/?range=today|week|month or date_from&date_to"""

    def get(self, request):
        _require_manager(request)
        store = get_user_store(request)
        date_from, date_to = _parse_sales_range(request, store)
        if date_from is None:
            return Response(
                {"detail": "range (today/week/month) または date_from, date_to を指定してください"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(get_sales_summary(store, date_from, date_to))


@document_object_api_view
class SalesExportView(APIView):
    """GET /api/op/sales-export.csv?range=..."""

    def get(self, request):
        _require_manager(request)
        store = get_user_store(request)
        date_from, date_to = _parse_sales_range(request, store)
        if date_from is None:
            return Response(
                {"detail": "range (today/week/month) または date_from, date_to を指定してください"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from django.http import HttpResponse
        csv_content = get_sales_csv(store, date_from, date_to)
        resp = HttpResponse(csv_content, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = (
            f'attachment; filename="sales_{date_from}_{date_to}.csv"'
        )
        return resp


def _parse_sales_dashboard_filters(request):
    """cast / room / payment_method のオプションフィルタを解析する（不正値は無視して絞り込みなし扱い）。"""
    def _int_or_none(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    cast_id = _int_or_none(request.query_params.get("cast"))
    room_id = _int_or_none(request.query_params.get("room"))
    payment_method = request.query_params.get("payment_method") or None
    if payment_method not in Order.PaymentMethod.values:
        payment_method = None
    return cast_id, room_id, payment_method


@document_object_api_view
class SalesDashboardView(APIView):
    """GET /api/op/sales-dashboard/?range=today|week|month or date_from&date_to&cast=&room=&payment_method=

    Phase 3-D: manager向け売上集計ダッシュボード。既存 SalesSummaryView（/op/sales-summary/、Sales.vue用）
    とは独立した別APIで、決済方法別/キャスト別（給与見込み込み）/部屋別の内訳を追加で返す。
    """

    def get(self, request):
        _require_manager(request)
        store = get_user_store(request)
        date_from, date_to = _parse_sales_range(request, store)
        if date_from is None:
            return Response(
                {"detail": "range (today/week/month) または date_from, date_to を指定してください"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        cast_id, room_id, payment_method = _parse_sales_dashboard_filters(request)
        return Response(get_sales_dashboard(store, date_from, date_to, cast_id, room_id, payment_method))


@document_object_api_view
class SalesDashboardExportView(APIView):
    """GET /api/op/sales-dashboard-export.csv?range=... または date_from&date_to&cast=&room=&payment_method=

    集計値（サマリー/決済方法別/キャスト別/部屋別/日別）をセクション区切りのCSVで出力する。
    """

    def get(self, request):
        _require_manager(request)
        store = get_user_store(request)
        date_from, date_to = _parse_sales_range(request, store)
        if date_from is None:
            return Response(
                {"detail": "range (today/week/month) または date_from, date_to を指定してください"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        cast_id, room_id, payment_method = _parse_sales_dashboard_filters(request)
        csv_content = get_sales_dashboard_csv(store, date_from, date_to, cast_id, room_id, payment_method)
        resp = HttpResponse(csv_content, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = (
            f'attachment; filename="sales_dashboard_{date_from}_{date_to}.csv"'
        )
        return resp


@document_object_api_view
class CustomerExportView(APIView):
    """GET /api/op/customers-export.csv — 現在の店舗の顧客一覧をCSV出力（manager限定）"""

    def get(self, request):
        _require_manager(request)
        store = get_user_store(request)

        output = io.StringIO()
        output.write("\ufeff")  # BOM
        writer = csv.writer(output)
        writer.writerow(["ID", "名前", "電話番号", "フラグ", "出禁種別", "顧客メモ", "運営メモ"])
        for c in Customer.objects.filter(store=store).order_by("id"):
            writer.writerow([
                c.id,
                c.display_name,
                c.phone,
                c.get_flag_display(),
                c.get_ban_type_display(),
                c.memo,
                c.staff_memo,
            ])

        from django.http import HttpResponse
        resp = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="customers.csv"'
        return resp


# ──────────────────────────────────────
# Daily Settlement — manager only
# ──────────────────────────────────────

@document_object_api_view
class DailySettlementView(APIView):
    """GET /api/op/daily-settlement/?date=YYYY-MM-DD"""

    def _parse_date(self, request):
        date_str = request.query_params.get("date") or request.data.get("date")
        if not date_str:
            return None, Response(
                {"detail": "date は必須です"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            return date_type.fromisoformat(date_str), None
        except ValueError:
            return None, Response(
                {"detail": "date の形式が不正です（YYYY-MM-DD）"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    def get(self, request):
        _require_manager(request)
        store = get_user_store(request)

        d, err = self._parse_date(request)
        if err:
            return err
        date_str = d.isoformat()

        # LOCKED ならスナップショットを返す
        settlement = DailySettlement.objects.filter(store=store, date=d).first()
        if settlement and settlement.status == DailySettlement.Status.LOCKED:
            snap = settlement.snapshot_json or {}
            snap["settlement_status"] = "LOCKED"
            snap["locked_at"] = settlement.locked_at.isoformat() if settlement.locked_at else None
            snap["locked_by"] = settlement.locked_by.username if settlement.locked_by else None
            return Response(snap)

        # 出勤キャスト: ShiftAssignment ベース
        shifts = (
            ShiftAssignment.objects
            .filter(store=store, date=d)
            .select_related("cast", "room")
        )
        cast_ids = set()
        cast_shifts = {}
        for s in shifts:
            cast_ids.add(s.cast_id)
            if s.cast_id not in cast_shifts:
                cast_shifts[s.cast_id] = []
            cast_shifts[s.cast_id].append(
                f"{str(s.start_time)[:5]}-"
                f"{format_extended_time(s.end_time, s.end_day_offset)}"
            )

        if not cast_ids:
            return Response({"date": date_str, "rows": [], "totals": {}})

        casts = {c.id: c for c in Cast.objects.filter(pk__in=cast_ids)}

        # DONE 注文
        done_orders = get_done_orders_for_business_range(store, d, d).filter(
            cast_id__in=cast_ids,
        )
        from collections import defaultdict
        orders_by_cast = defaultdict(list)
        for o in done_orders:
            orders_by_cast[o.cast_id].append(o)

        # 雑費
        expenses = CastExpense.objects.filter(store=store, date=d, cast_id__in=cast_ids)
        expenses_by_cast = defaultdict(list)
        for exp in expenses:
            expenses_by_cast[exp.cast_id].append(exp)

        # ポイント
        from django.db.models import Sum
        point_agg = (
            PointLog.objects
            .filter(store=store, date=d, cast_id__in=cast_ids)
            .values("cast_id")
            .annotate(total=Sum("points"))
        )
        points_by_cast = {row["cast_id"]: row["total"] or 0 for row in point_agg}

        import math

        rows = []
        total_course = 0
        total_options = 0
        total_back = 0
        total_expense = 0
        total_points = 0
        total_cash_count = 0
        total_cash_sales = 0
        total_net = 0

        for cast_id in sorted(cast_ids, key=lambda cid: casts[cid].name):
            cast = casts[cast_id]
            cast_orders = orders_by_cast.get(cast_id, [])
            order_count = len(cast_orders)

            course_sales = sum(o.course_price for o in cast_orders)
            options_sales = sum(o.options_price for o in cast_orders)

            course_back = math.floor(course_sales * cast.course_back_rate / 100)
            option_back = options_sales if cast.option_fullback_enabled else 0
            back_amount = course_back + option_back

            # 雑費控除
            expense_total = 0
            for exp in expenses_by_cast.get(cast_id, []):
                if exp.per_order:
                    expense_total += exp.amount * order_count
                else:
                    expense_total += exp.amount

            # ポイント
            point_total = points_by_cast.get(cast_id, 0)

            # 現金情報（キャスト預かり分を振込額から控除）
            cash_orders = [o for o in cast_orders if o.payment_method == Order.PaymentMethod.CASH]
            cash_order_count = len(cash_orders)
            cash_sales_total = sum(o.total_price for o in cash_orders)

            net_pay = back_amount - expense_total + point_total - cash_sales_total

            shift_text = " / ".join(cast_shifts.get(cast_id, []))

            rows.append({
                "cast_id": cast.id,
                "cast_name": cast.name,
                "shift": shift_text,
                "order_count": order_count,
                "course_sales": course_sales,
                "options_sales": options_sales,
                "course_back_rate": cast.course_back_rate,
                "option_fullback_enabled": cast.option_fullback_enabled,
                "back_amount": back_amount,
                "expense_total": expense_total,
                "point_total": point_total,
                "cash_order_count": cash_order_count,
                "cash_sales_total": cash_sales_total,
                "net_pay": net_pay,
            })

            total_course += course_sales
            total_options += options_sales
            total_back += back_amount
            total_expense += expense_total
            total_points += point_total
            total_cash_count += cash_order_count
            total_cash_sales += cash_sales_total
            total_net += net_pay

        return Response({
            "date": date_str,
            "settlement_status": "OPEN",
            "locked_at": None,
            "locked_by": None,
            "rows": rows,
            "totals": {
                "course_sales": total_course,
                "options_sales": total_options,
                "back_amount": total_back,
                "expense_total": total_expense,
                "point_total": total_points,
                "cash_order_count": total_cash_count,
                "cash_sales_total": total_cash_sales,
                "net_pay": total_net,
            },
        })


@document_object_api_view
class DailySettlementLockView(APIView):
    """POST /api/op/daily-settlement/lock/ — 清算確定
    body: { date, rows, totals }
    フロントが表示中のスナップショットをそのまま送る。
    """

    def post(self, request):
        _require_manager(request)
        store = get_user_store(request)

        date_str = request.data.get("date")
        if not date_str:
            return Response({"detail": "date は必須です"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            d = date_type.fromisoformat(date_str)
        except ValueError:
            return Response({"detail": "date の形式が不正です"}, status=status.HTTP_400_BAD_REQUEST)

        existing = DailySettlement.objects.filter(store=store, date=d, status=DailySettlement.Status.LOCKED).first()
        if existing:
            return Response({"detail": "この日は既に確定済みです"}, status=status.HTTP_400_BAD_REQUEST)

        snapshot = {
            "date": date_str,
            "rows": request.data.get("rows", []),
            "totals": request.data.get("totals", {}),
        }

        settlement, _ = DailySettlement.objects.get_or_create(
            store=store, date=d,
            defaults={"status": DailySettlement.Status.OPEN},
        )
        settlement.status = DailySettlement.Status.LOCKED
        settlement.snapshot_json = snapshot
        settlement.locked_at = timezone.now()
        settlement.locked_by = request.user
        settlement.save()

        return Response({"ok": True, "status": "LOCKED", "date": date_str})


@document_object_api_view
class DailySettlementUnlockView(APIView):
    """POST /api/op/daily-settlement/unlock/ — 清算ロック解除"""

    def post(self, request):
        _require_manager(request)
        store = get_user_store(request)

        date_str = request.data.get("date")
        if not date_str:
            return Response({"detail": "date は必須です"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            d = date_type.fromisoformat(date_str)
        except ValueError:
            return Response({"detail": "date の形式が不正です"}, status=status.HTTP_400_BAD_REQUEST)

        settlement = DailySettlement.objects.filter(store=store, date=d).first()
        if not settlement or settlement.status != DailySettlement.Status.LOCKED:
            return Response({"detail": "この日は確定されていません"}, status=status.HTTP_400_BAD_REQUEST)

        settlement.status = DailySettlement.Status.OPEN
        settlement.snapshot_json = {}
        settlement.locked_at = None
        settlement.locked_by = None
        settlement.save()

        return Response({"ok": True, "status": "OPEN", "date": date_str})


@document_object_api_view
class DailySettlementExportView(APIView):
    """GET /api/op/daily-settlement/export/?date=YYYY-MM-DD — CSV出力"""

    def get(self, request):
        _require_manager(request)
        store = get_user_store(request)

        date_str = request.query_params.get("date")
        if not date_str:
            return Response({"detail": "date は必須です"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            d = date_type.fromisoformat(date_str)
        except ValueError:
            return Response({"detail": "date の形式が不正です"}, status=status.HTTP_400_BAD_REQUEST)

        # LOCKED ならスナップショット、OPEN なら都度計算
        settlement = DailySettlement.objects.filter(store=store, date=d).first()
        if settlement and settlement.status == DailySettlement.Status.LOCKED:
            data = settlement.snapshot_json or {}
        else:
            # DailySettlementView の GET を再利用
            view = DailySettlementView()
            view._parse_date = lambda req: (d, None)
            fake_resp = view.get(request)
            data = fake_resp.data

        rows = data.get("rows", [])
        totals = data.get("totals", {})
        settlement_status = data.get("settlement_status", "OPEN")

        output = io.StringIO()
        output.write("\ufeff")  # BOM
        writer = csv.writer(output)

        # ヘッダー
        writer.writerow([
            "キャスト名", "出勤", "予約件数",
            "コース売上", "オプション売上",
            "バック率(%)", "OP全額バック",
            "バック額", "雑費", "ポイント",
            "現金件数", "現金預り", "振込額",
        ])

        for r in rows:
            writer.writerow([
                r.get("cast_name", ""),
                r.get("shift", ""),
                r.get("order_count", 0),
                r.get("course_sales", 0),
                r.get("options_sales", 0),
                r.get("course_back_rate", 0),
                "○" if r.get("option_fullback_enabled") else "",
                r.get("back_amount", 0),
                r.get("expense_total", 0),
                r.get("point_total", 0),
                r.get("cash_order_count", 0),
                r.get("cash_sales_total", 0),
                r.get("net_pay", 0),
            ])

        # 合計行
        writer.writerow([
            "合計", "", "",
            totals.get("course_sales", 0),
            totals.get("options_sales", 0),
            "", "",
            totals.get("back_amount", 0),
            totals.get("expense_total", 0),
            totals.get("point_total", 0),
            totals.get("cash_order_count", 0),
            totals.get("cash_sales_total", 0),
            totals.get("net_pay", 0),
        ])

        # 状態行
        writer.writerow([])
        writer.writerow(["状態", settlement_status])

        resp = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="daily-settlement-{date_str}.csv"'
        return resp


# ──────────────────────────────────────
# LINE Webhook
# ──────────────────────────────────────

@extend_schema(operation_id="line_webhook", request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def line_webhook(request):
    """POST /api/webhook/line/ — レガシー (グローバル env) LINE webhook"""
    channel_secret = getattr(settings, "LINE_CHANNEL_SECRET", "")
    channel_token = getattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "")
    return _handle_line_webhook(request, channel_secret, channel_token)


@extend_schema(operation_id="line_webhook_store", request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def line_webhook_store(request, webhook_token):
    """POST /api/webhook/line/<webhook_token>/ — Store 別 LINE webhook"""
    store = Store.objects.filter(line_webhook_token=webhook_token, line_is_enabled=True).first()
    if store is None:
        return Response({"detail": "Unknown webhook"}, status=status.HTTP_403_FORBIDDEN)
    return _handle_line_webhook(request, store.line_channel_secret, store.line_channel_access_token, store=store)


def _handle_line_webhook(request, channel_secret, channel_token, store=None):
    import hashlib
    import hmac
    import base64

    # 署名検証
    signature = request.headers.get("X-Line-Signature", "")
    if channel_secret:
        body_bytes = request.body
        hash_val = hmac.new(
            channel_secret.encode("utf-8"),
            body_bytes,
            hashlib.sha256,
        ).digest()
        expected = base64.b64encode(hash_val).decode("utf-8")
        if not hmac.compare_digest(signature, expected):
            return Response({"detail": "Invalid signature"}, status=status.HTTP_403_FORBIDDEN)

    body = request.data
    events = body.get("events", [])

    for event in events:
        event_type = event.get("type")
        reply_token = event.get("replyToken")
        source = event.get("source", {})
        line_user_id = source.get("userId", "")

        if event_type == "follow":
            _line_reply(channel_token, reply_token,
                        "Roomink LINE連携へようこそ！\n管理画面に表示されている連携コード（6桁）を送信してください。")

        elif event_type == "message":
            msg = event.get("message", {})
            if msg.get("type") != "text":
                continue
            code = msg.get("text", "").strip().upper()

            # 既に別 Cast に連携済みの LINE userId か
            existing = Cast.objects.filter(line_user_id=line_user_id).first()
            if existing:
                _line_reply(channel_token, reply_token,
                            f"既に {existing.name} さんとして連携済みです。\n再連携が必要な場合は管理者にお問い合わせください。")
                continue

            # コード照合 — store 指定がある場合はその store のキャストのみ
            cast_qs = Cast.objects.filter(line_link_code=code, line_user_id__isnull=True)
            if store:
                cast_qs = cast_qs.filter(store=store)
            cast = cast_qs.first()
            if cast is None:
                _line_reply(channel_token, reply_token,
                            "無効なコードです。コードをご確認のうえ、再度お試しください。")
                continue

            # 連携実行
            cast.line_user_id = line_user_id
            cast.line_linked_at = timezone.now()
            cast.save(update_fields=["line_user_id", "line_linked_at"])

            app_url = os.getenv("FRONTEND_URL", "https://roomink.netlify.app")
            _line_reply(channel_token, reply_token,
                        f"連携が完了しました！\n{cast.name}さん、よろしくお願いします。\n出勤リマインド通知をお届けします。\n\nアプリに戻る:\n{app_url}/cast/mypage")

    return Response({"ok": True})


def _line_reply(channel_token, reply_token, text):
    """LINE Reply Message API でテキストを返す"""
    if not channel_token or not reply_token:
        logger.info("LINE reply skip (no token): %s", text[:40])
        return
    import requests as http_requests
    http_requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {channel_token}",
        },
        json={
            "replyToken": reply_token,
            "messages": [{"type": "text", "text": text}],
        },
        timeout=5,
    )


# ──────────────────────────────────────
# LINE 連携コード再発行
# ──────────────────────────────────────

@document_object_api_view
class CastLineLinkView(APIView):
    """GET  /api/cast/line-link/ — 連携状態取得
       POST /api/cast/line-link/regenerate/ — 連携コード再発行
       POST /api/cast/line-link/unlink/ — 連携解除
    """

    def get(self, request):
        cast = getattr(request.user, "cast_profile", None)
        if cast is None:
            return Response({"detail": "キャストが紐づいていません"}, status=status.HTTP_403_FORBIDDEN)
        return Response({
            "line_link_code": cast.line_link_code,
            "line_linked": cast.line_user_id is not None,
            "line_linked_at": cast.line_linked_at,
        })

    def post(self, request):
        cast = getattr(request.user, "cast_profile", None)
        if cast is None:
            return Response({"detail": "キャストが紐づいていません"}, status=status.HTTP_403_FORBIDDEN)

        action = request.data.get("action", "regenerate")

        if action == "unlink":
            cast.line_user_id = None
            cast.line_linked_at = None
            cast.line_link_code = generate_line_link_code()
            cast.save(update_fields=["line_user_id", "line_linked_at", "line_link_code"])
            return Response({"ok": True, "line_link_code": cast.line_link_code, "line_linked": False})

        # regenerate
        if cast.line_user_id:
            return Response({"detail": "連携済みです。解除してから再発行してください。"}, status=status.HTTP_400_BAD_REQUEST)
        cast.line_link_code = generate_line_link_code()
        cast.save(update_fields=["line_link_code"])
        return Response({"ok": True, "line_link_code": cast.line_link_code})


# ──────────────────────────────────────
# LINE アラート API（operator 向け）
# ──────────────────────────────────────

@document_object_api_view
class LineAlertsView(APIView):
    """GET /api/op/line-alerts/ — 当日の LINE 未連携 cast + 送信失敗を返す"""

    def get(self, request):
        store = get_user_store(request)
        today = date_type.today()
        now_local = timezone.localtime()

        # 当日出勤予定で LINE 未連携の Cast
        today_shift_cast_ids = (
            ShiftAssignment.objects
            .filter(store=store, date=today)
            .values_list("cast_id", flat=True)
        )
        unlinked = (
            Cast.objects
            .filter(id__in=today_shift_cast_ids, line_user_id__isnull=True)
            .values("id", "name")
        )
        # 各 unlinked cast の最初のシフト時間を取得
        unlinked_list = []
        for c in unlinked:
            shift = (
                ShiftAssignment.objects
                .filter(store=store, date=today, cast_id=c["id"])
                .order_by("start_time")
                .first()
            )
            unlinked_list.append({
                "id": c["id"],
                "name": c["name"],
                "start_time": str(shift.start_time)[:5] if shift else None,
            })

        # 当日の送信失敗ログ
        failed = (
            LineNotificationLog.objects
            .filter(
                store=store,
                shift_assignment__date=today,
                status=LineNotificationLog.Status.FAILED,
            )
            .select_related("cast")
            .order_by("-sent_at")[:20]
        )
        failed_list = [
            {
                "id": f.id,
                "cast_name": f.cast.name,
                "notification_type": f.notification_type,
                "error_message": f.error_message[:100],
                "sent_at": f.sent_at.isoformat(),
            }
            for f in failed
        ]

        # 当日シフトで開始時刻を過ぎているのに未打刻（未出勤）の Cast
        not_clocked_in = (
            ShiftAssignment.objects
            .filter(
                store=store,
                date=today,
                clocked_in_at__isnull=True,
                start_time__lte=now_local.time(),
            )
            .select_related("cast")
            .order_by("start_time")
        )
        not_clocked_in_list = [
            {
                "id": s.id,
                "cast_id": s.cast_id,
                "name": s.cast.name,
                "start_time": str(s.start_time)[:5],
            }
            for s in not_clocked_in
        ]

        return Response({
            "unlinked_casts": unlinked_list,
            "failed_notifications": failed_list,
            "not_clocked_in_casts": not_clocked_in_list,
        })


# ──────────────────────────────────────
# Store LINE設定 (manager only)
# ──────────────────────────────────────

@document_object_api_view
class StoreLineSettingsView(APIView):
    """GET / PATCH /api/op/line-settings/"""

    @staticmethod
    def _webhook_url(request, store):
        origin = request.build_absolute_uri("/").rstrip("/")
        return f"{origin}/api/webhook/line/{store.line_webhook_token}/"

    def get(self, request):
        _require_manager(request)
        store = get_user_store(request)
        return Response({
            "line_is_enabled": store.line_is_enabled,
            "line_add_friend_url": store.line_add_friend_url,
            "line_channel_secret": store.line_channel_secret,
            "line_channel_access_token": store.line_channel_access_token,
            "line_webhook_url": self._webhook_url(request, store),
            "line_morning_enabled": store.line_morning_enabled,
            "line_morning_time": store.line_morning_time.strftime("%H:%M") if store.line_morning_time else "09:00",
            "line_two_hours_enabled": store.line_two_hours_enabled,
            "line_fifteen_minutes_enabled": store.line_fifteen_minutes_enabled,
        })

    def patch(self, request):
        _require_manager(request)
        store = get_user_store(request)
        fields = []
        for key in ("line_is_enabled", "line_add_friend_url",
                     "line_channel_secret", "line_channel_access_token",
                     "line_morning_enabled", "line_two_hours_enabled",
                     "line_fifteen_minutes_enabled"):
            if key in request.data:
                setattr(store, key, request.data[key])
                fields.append(key)
        if "line_morning_time" in request.data:
            from datetime import time as dt_time
            val = request.data["line_morning_time"]
            if isinstance(val, str):
                parts = val.split(":")
                val = dt_time(int(parts[0]), int(parts[1]))
            store.line_morning_time = val
            fields.append("line_morning_time")
        if fields:
            store.save(update_fields=fields)
        return Response({
            "line_is_enabled": store.line_is_enabled,
            "line_add_friend_url": store.line_add_friend_url,
            "line_channel_secret": store.line_channel_secret,
            "line_channel_access_token": store.line_channel_access_token,
            "line_webhook_url": self._webhook_url(request, store),
            "line_morning_enabled": store.line_morning_enabled,
            "line_morning_time": store.line_morning_time.strftime("%H:%M") if store.line_morning_time else "09:00",
            "line_two_hours_enabled": store.line_two_hours_enabled,
            "line_fifteen_minutes_enabled": store.line_fifteen_minutes_enabled,
        })


@document_object_api_view
class StorePaymentFeeSettingsView(APIView):
    """GET / PATCH /api/op/payment-fee-settings/ — 決済手数料率（参考値）の設定。manager のみ。
    ここで設定した値は売上集計(/op/sales-dashboard/)・退勤提出の手数料見込み計算にのみ使用し、
    確定精算・給与確定・DailySettlementViewには一切接続しない。"""

    def get(self, request):
        _require_manager(request)
        store = get_user_store(request)
        return Response({
            "cash_fee_rate": store.cash_fee_rate,
            "paypay_fee_rate": store.paypay_fee_rate,
            "card_fee_rate": store.card_fee_rate,
        })

    def patch(self, request):
        _require_manager(request)
        store = get_user_store(request)
        fields = []
        for key in ("cash_fee_rate", "paypay_fee_rate", "card_fee_rate"):
            if key in request.data:
                try:
                    value = int(request.data[key])
                except (TypeError, ValueError):
                    return Response(
                        {"detail": f"{key} は0〜100の整数で指定してください"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if value < 0 or value > 100:
                    return Response(
                        {"detail": f"{key} は0〜100の範囲で指定してください"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                setattr(store, key, value)
                fields.append(key)
        if fields:
            store.save(update_fields=fields)
        return Response({
            "cash_fee_rate": store.cash_fee_rate,
            "paypay_fee_rate": store.paypay_fee_rate,
            "card_fee_rate": store.card_fee_rate,
        })


# ──────────────────────────────────────
# 週次シフト入力 / タイムライン並び替え / SMS設定・履歴
# ──────────────────────────────────────

def _require_staff_or_manager(request):
    """staff / manager 以外（cast・customer）は PermissionDenied。"""
    profile = getattr(request.user, "profile", None)
    if profile is None or profile.role not in (UserProfile.Role.STAFF, UserProfile.Role.MANAGER):
        from rest_framework.exceptions import PermissionDenied
        raise PermissionDenied("この機能はスタッフ／マネージャーのみ利用できます。")


def _parse_date(value, field="date"):
    """YYYY-MM-DD → date。不正なら ValidationError。"""
    from rest_framework.exceptions import ValidationError
    if not value:
        raise ValidationError({field: "日付を指定してください（YYYY-MM-DD）"})
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError({field: f"日付の形式が不正です: {value}"})


WEEKDAY_LABELS = ["月", "火", "水", "木", "金", "土", "日"]


@document_object_api_view
class WeeklyShiftView(APIView):
    """GET/POST /api/op/shifts/weekly/
    1キャスト×1週間分のシフトをまとめて新規登録する。staff/manager のみ。
    既存シフトの上書き・削除はしない（新規追加のみ）。"""

    def get(self, request):
        _require_staff_or_manager(request)
        store = get_user_store(request)

        week_start = _parse_date(request.query_params.get("week_start"), "week_start")
        cast_id = request.query_params.get("cast")
        if not cast_id:
            return Response({"detail": "cast を指定してください"}, status=status.HTTP_400_BAD_REQUEST)

        cast = Cast.objects.filter(pk=cast_id, store=store).first()
        if cast is None:
            return Response({"detail": "対象のキャストが見つかりません"}, status=status.HTTP_404_NOT_FOUND)

        week_end = week_start + timedelta(days=6)
        existing = (
            ShiftAssignment.objects
            .filter(store=store, cast=cast, date__gte=week_start, date__lte=week_end)
            .select_related("room")
            .order_by("date", "start_time")
        )
        by_date = defaultdict(list)
        for s in existing:
            by_date[s.date].append(s)

        days = []
        for i in range(7):
            d = week_start + timedelta(days=i)
            days.append({
                "date": d.isoformat(),
                "weekday": WEEKDAY_LABELS[d.weekday()],
                "existing_shifts": ShiftAssignmentSerializer(by_date.get(d, []), many=True).data,
            })

        return Response({
            "cast": cast.id,
            "cast_name": cast.name,
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "days": days,
        })

    def post(self, request):
        _require_staff_or_manager(request)
        store = get_user_store(request)

        week_start = _parse_date(request.data.get("week_start"), "week_start")
        week_end = week_start + timedelta(days=6)

        cast = Cast.objects.filter(pk=request.data.get("cast"), store=store).first()
        if cast is None:
            return Response({"detail": "対象のキャストが見つかりません"}, status=status.HTTP_404_NOT_FOUND)

        items = request.data.get("items")
        if not isinstance(items, list) or not items:
            return Response({"detail": "items を1件以上指定してください"}, status=status.HTTP_400_BAD_REQUEST)

        errors = []
        payloads = []
        for item in items:
            if not isinstance(item, dict) or not item.get("enabled"):
                continue
            d = _parse_date(item.get("date"), "date")
            if d < week_start or d > week_end:
                errors.append({"date": item.get("date"), "detail": "指定した週の範囲外です"})
                continue
            payloads.append({
                "date": d.isoformat(),
                "cast": cast.id,
                "room": item.get("room"),
                "start_time": item.get("start_time"),
                "end_time": item.get("end_time"),
                "end_day_offset": item.get("end_day_offset", 0),
                "daily_memo": item.get("daily_memo") or "",
            })

        if not payloads and not errors:
            return Response(
                {"detail": "出勤する日が1日も選択されていません"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 全件バリデーション（既存シフト衝突は ShiftAssignmentSerializer.validate が検出）
        serializers_ok = []
        for p in payloads:
            ser = ShiftAssignmentSerializer(data=p, context={"store": store})
            if ser.is_valid():
                serializers_ok.append(ser)
            else:
                detail = "; ".join(
                    f"{k}: {' '.join(str(x) for x in v)}" if isinstance(v, list) else f"{k}: {v}"
                    for k, v in ser.errors.items()
                )
                errors.append({"date": p["date"], "detail": detail})

        # リクエスト内での重複（翌日まで続くシフトも含む）
        seen_intervals = []
        for ser in serializers_ok:
            v = ser.validated_data
            start_at, end_at = build_business_interval(
                v["date"],
                v["start_time"],
                v["end_time"],
                end_day_offset=v.get("end_day_offset", 0),
                timezone_name=store.timezone,
            )
            for other_start, other_end in seen_intervals:
                if intervals_overlap(start_at, end_at, other_start, other_end):
                    errors.append({
                        "date": v["date"].isoformat(),
                        "detail": "同じリクエスト内で時間が重複しています",
                    })
            seen_intervals.append((start_at, end_at))

        if errors:
            return Response(
                {"detail": "登録できない日があるため、1件も登録していません", "errors": errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            created = [ser.save(store=store) for ser in serializers_ok]

        return Response(
            {
                "created_count": len(created),
                "created": ShiftAssignmentSerializer(created, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )


@document_object_api_view
class ScheduleCastOrderView(APIView):
    """GET/POST /api/op/schedule-cast-order/
    タイムライン（キャスト別表示）の出勤セラピスト表示順。
    display_order のみ更新し、シフト時間・部屋には影響しない。staff/manager のみ。"""

    def get(self, request):
        _require_staff_or_manager(request)
        store = get_user_store(request)
        d = _parse_date(request.query_params.get("date"))

        shifts = (
            ShiftAssignment.objects
            .filter(store=store, date=d)
            .select_related("cast", "room")
        )
        rows = [
            {
                "shift_assignment_id": s.id,
                "cast_id": s.cast_id,
                "cast_name": s.cast.name,
                "room_name": s.room.name if s.room else "",
                "start_time": s.start_time,
                "end_time": s.end_time,
                "end_time_extended": format_extended_time(s.end_time, s.end_day_offset),
                "display_order": s.display_order,
            }
            for s in shifts
        ]
        # 未設定(0)は後ろ、それ以外は display_order 順。タイムライン表示と同じ並び。
        rows.sort(key=lambda r: (
            1 if not r["display_order"] else 0,
            r["display_order"] or 0,
            r["cast_name"],
        ))
        return Response({"date": d.isoformat(), "items": rows})

    def post(self, request):
        _require_staff_or_manager(request)
        store = get_user_store(request)
        d = _parse_date(request.data.get("date"))

        items = request.data.get("items")
        if not isinstance(items, list):
            return Response({"detail": "items を指定してください"}, status=status.HTTP_400_BAD_REQUEST)

        # 他店舗・他日付のシフトを並び替えられないよう、対象を store+date に限定する
        allowed = {
            s.id: s for s in ShiftAssignment.objects.filter(store=store, date=d)
        }
        updates = []
        for item in items:
            if not isinstance(item, dict):
                continue
            sid = item.get("shift_assignment_id")
            shift = allowed.get(sid)
            if shift is None:
                return Response(
                    {"detail": f"対象外のシフトが含まれています (id={sid})"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                order_value = int(item.get("display_order") or 0)
            except (TypeError, ValueError):
                return Response(
                    {"detail": "display_order は整数で指定してください"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if order_value < 0 or order_value > 32767:
                return Response(
                    {"detail": "display_order は0以上の整数で指定してください"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            shift.display_order = order_value
            updates.append(shift)

        if updates:
            ShiftAssignment.objects.bulk_update(updates, ["display_order"])

        return Response({"updated_count": len(updates)})


@document_object_api_view
class OrderSmsLogsView(APIView):
    """GET /api/op/orders/<pk>/sms-logs/ — 予約ごとのSMS送信履歴。staff/manager のみ・自店舗のみ。"""

    def get(self, request, pk):
        _require_staff_or_manager(request)
        store = get_user_store(request)

        order = Order.objects.filter(pk=pk, store=store).first()
        if order is None:
            return Response({"detail": "対象の予約が見つかりません"}, status=status.HTTP_404_NOT_FOUND)

        logs = (
            SmsLog.objects
            .filter(order=order)
            .select_related("created_by")
            .order_by("-sent_at", "-id")
        )
        return Response(SmsLogSerializer(logs, many=True).data)


@document_object_api_view
class CustomerInvitationStatusView(APIView):
    """顧客アカウント招待の状態確認と、運営による安全な再発行。"""

    def _customer(self, request, pk):
        _require_staff_or_manager(request)
        store = get_user_store(request)
        customer = Customer.objects.filter(pk=pk, store=store).first()
        if customer is None:
            from rest_framework.exceptions import NotFound
            raise NotFound("対象の顧客が見つかりません")
        return customer

    def get(self, request, pk):
        return Response(serialize_invitation_status(self._customer(request, pk)))

    def post(self, request, pk):
        customer = self._customer(request, pk)
        if customer.user_id:
            return Response(
                {"detail": "この顧客はアカウント設定済みです。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order = (
            customer.orders
            .exclude(status__in=[Order.Status.REQUESTED, Order.Status.CANCELLED])
            .order_by("-created_at")
            .first()
        )
        if order is None and not customer.account_invitations.exists():
            return Response(
                {"detail": "予約確定後に初回案内を発行できます。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        notify_customer_account(customer, order=order, created_by=request.user, force=True)
        return Response(serialize_invitation_status(customer))


@document_object_api_view
class SmsTemplateSettingsView(APIView):
    """GET/PUT /api/op/sms-templates/
    支払方法別の予約確認SMS文面設定。閲覧は staff/manager、編集は manager のみ。"""

    TEMPLATE_TYPE = SmsTemplate.TemplateType.RESERVATION_CONFIRMATION

    def _payload(self, store):
        existing = {
            t.payment_method: t
            for t in SmsTemplate.objects.filter(store=store, template_type=self.TEMPLATE_TYPE)
        }
        items = []
        for value, label in Order.PaymentMethod.choices:
            tpl = existing.get(value)
            items.append({
                "payment_method": value,
                "payment_method_label": label,
                "body": tpl.body if tpl else "",
                "is_active": tpl.is_active if tpl else False,
                "updated_by_name": (
                    (tpl.updated_by.get_full_name() or tpl.updated_by.username)
                    if tpl and tpl.updated_by else ""
                ),
                "updated_at": tpl.updated_at if tpl else None,
                "default_body": _default_sms_preview(value),
            })
        return {
            "template_type": self.TEMPLATE_TYPE,
            "placeholders": list(SmsTemplate.PLACEHOLDERS),
            "items": items,
        }

    def get(self, request):
        _require_staff_or_manager(request)
        store = get_user_store(request)
        return Response(self._payload(store))

    def put(self, request):
        _require_manager(request)
        store = get_user_store(request)

        items = request.data.get("items")
        if not isinstance(items, list):
            return Response({"detail": "items を指定してください"}, status=status.HTTP_400_BAD_REQUEST)

        valid_methods = set(Order.PaymentMethod.values)
        with transaction.atomic():
            for item in items:
                if not isinstance(item, dict):
                    continue
                pm = item.get("payment_method")
                if pm not in valid_methods:
                    return Response(
                        {"detail": f"支払方法が不正です: {pm}"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                body = item.get("body") or ""
                is_active = bool(item.get("is_active"))
                if is_active and not body.strip():
                    return Response(
                        {"detail": "有効にする場合は本文を入力してください"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                SmsTemplate.objects.update_or_create(
                    store=store,
                    template_type=self.TEMPLATE_TYPE,
                    payment_method=pm,
                    defaults={
                        "body": body,
                        "is_active": is_active,
                        "updated_by": request.user,
                    },
                )

        return Response(self._payload(store))
