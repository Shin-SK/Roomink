import csv
import io
import logging
import os
from datetime import date as date_type, timedelta

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
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

from .models import (
    CallLog, CallNote, Cast, CastAck, CastExpense, Course, Customer,
    CustomerMergeLog, DailySettlement, Discount, Extension, Medium,
    LineNotificationLog, NominationFee, Option, Order, OrderOption, PointLog,
    Room, ShiftAssignment, ShiftRequest, Store, StorePhoneNumber, UserProfile,
    generate_line_link_code,
)
from .serializers import (
    CastExpenseSerializer,
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
    build_customer_label,
    build_schedule_data,
    build_room_schedule_data,
)
from .utils.phone import normalize_phone

logger = logging.getLogger(__name__)
from .services.cast_user import ensure_user_profile, update_or_create_cast_with_user
from .services.customer_context import resolve_customer
from .services.pricing import recalculate_order_total
from .services.sales import get_sales_summary, get_sales_csv
from .services.notify import (
    notify_cast_order,
    notify_order_cancelled,
    notify_order_confirmed,
)


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


@api_view(["POST"])
def auth_logout(request):
    logout(request)
    return Response({"ok": True})


@api_view(["GET"])
@ensure_csrf_cookie
def auth_me(request):
    try:
        profile = UserProfile.objects.select_related("store").get(user=request.user)
    except UserProfile.DoesNotExist:
        return Response(
            {"detail": "プロフィールが未作成です。管理者に連絡してください。"},
            status=status.HTTP_403_FORBIDDEN,
        )
    store = profile.store
    return Response({
        "id": request.user.id,
        "username": request.user.username,
        "display_name": request.user.first_name or request.user.username,
        "avatar_url": profile.avatar_url,
        "store_id": store.id,
        "store_name": store.name,
        "role": profile.role,
    })


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
        notify_order_confirmed(order)
        notify_cast_order(order)
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
        notify_order_cancelled(order)
        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=["post"])
    def done(self, request, pk=None):
        order = self.get_object()
        if order.status not in (Order.Status.CONFIRMED, Order.Status.IN_PROGRESS):
            return Response(
                {"detail": f"ステータスが {order.get_status_display()} のため完了にできません"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.status = Order.Status.DONE
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


# ──────────────────────────────────────
# Customer — signup / mypage / booking
# ──────────────────────────────────────

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


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def customer_signup(request):
    """POST /api/cu/signup/ — 顧客アカウント作成"""
    from django.contrib.auth.models import User

    phone = normalize_phone((request.data.get("phone") or "").strip())
    password = request.data.get("password", "")
    display_name = (request.data.get("display_name") or "").strip()

    if not phone or not password:
        return Response(
            {"detail": "電話番号とパスワードは必須です"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if User.objects.filter(username=phone).exists():
        return Response(
            {"detail": "この電話番号は既に登録されています"},
            status=status.HTTP_409_CONFLICT,
        )

    store_id = request.data.get("store_id")
    if not store_id:
        return Response(
            {"detail": "store_id は必須です"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    store = Store.objects.filter(id=store_id).first()
    if store is None:
        return Response(
            {"detail": "指定された店舗が見つかりません"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    with transaction.atomic():
        user = User.objects.create_user(username=phone, password=password)
        customer, created = Customer.objects.get_or_create(
            store=store, phone=phone,
            defaults={"display_name": display_name},
        )
        if not created and customer.user_id is not None:
            user.delete()
            return Response(
                {"detail": "この電話番号は既に登録されています"},
                status=status.HTTP_409_CONFLICT,
            )
        customer.user = user
        if display_name and not customer.display_name:
            customer.display_name = display_name
        customer.save()

    login(request, user)
    return Response({"ok": True, "username": user.username}, status=status.HTTP_201_CREATED)


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


class CustomerAvailableSlotsView(APIView):
    """GET /api/cu/available-slots/?cast={id}&date={YYYY-MM-DD}"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from datetime import time as time_type, datetime, timedelta

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

        # シフト取得
        shifts = ShiftAssignment.objects.filter(store=store, date=d, cast=cast)

        # 30分刻みスロット生成
        slot_minutes = 30
        raw_slots = []
        for sh in shifts:
            current = datetime.combine(d, sh.start_time)
            end = datetime.combine(d, sh.end_time)
            while current + timedelta(minutes=slot_minutes) <= end:
                raw_slots.append((current.time(), (current + timedelta(minutes=slot_minutes)).time()))
                current += timedelta(minutes=slot_minutes)

        # 既存予約取得（CANCELLED以外）+ インターバル反映
        orders = Order.objects.filter(
            cast=cast,
            start__date=d,
            status__in=Order.ACTIVE_STATUSES,
        )
        interval = cast.interval_minutes or 0
        busy = []
        for o in orders:
            busy_end = (datetime.combine(d, o.end.time()) + timedelta(minutes=interval)).time()
            busy.append((o.start.time(), busy_end))

        # 重複除外
        slots = []
        for s_start, s_end in raw_slots:
            conflict = any(b_start < s_end and b_end > s_start for b_start, b_end in busy)
            if not conflict:
                slots.append({"start": s_start.strftime("%H:%M"), "end": s_end.strftime("%H:%M")})

        return Response({
            "date": date_str,
            "cast_id": cast.id,
            "cast_name": cast.name,
            "slots": slots,
        })


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

    def perform_create(self, serializer):
        serializer.save(store=get_user_store(self.request))


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

class OpShiftRequestViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OpShiftRequestSerializer
    queryset = ShiftRequest.objects.select_related("cast", "desired_room").order_by("-created_at")
    filterset_fields = {
        "date": ["exact", "gte", "lte"],
        "status": ["exact"],
        "cast": ["exact"],
    }
    ordering = ["-created_at"]

    def get_queryset(self):
        store = get_user_store(self.request)
        return super().get_queryset().filter(store=store)

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

        # ShiftAssignment 作成（重複チェックは serializer に任せる）
        from .serializers import ShiftAssignmentSerializer
        sa_data = {
            "date": obj.date,
            "cast": obj.cast_id,
            "room": room.id,
            "start_time": str(obj.start_time),
            "end_time": str(obj.end_time),
        }
        sa_serializer = ShiftAssignmentSerializer(data=sa_data)
        if not sa_serializer.is_valid():
            return Response(sa_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        sa_serializer.save(store=obj.store)

        obj.status = ShiftRequest.Status.APPROVED
        obj.admin_memo = admin_memo
        obj.save(update_fields=["status", "admin_memo", "updated_at"])
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
        obj.save(update_fields=["status", "admin_memo", "updated_at"])
        return Response(OpShiftRequestSerializer(obj).data)



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

CTI_SHARED_TOKEN = os.getenv("CTI_SHARED_TOKEN", "dev-token")


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
        if token != CTI_SHARED_TOKEN:
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
            store_phone = StorePhoneNumber.objects.select_related("store").get(phone=to_phone)
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
# Twilio Webhook
# ──────────────────────────────────────

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
    call_sid = request.data.get("CallSid", "")
    raw_from = request.data.get("From", "")
    raw_to = request.data.get("To", "")
    call_status = request.data.get("CallStatus", "")

    logger.info("Twilio voice webhook: CallSid=%s From=%s To=%s Status=%s", call_sid, raw_from, raw_to, call_status)

    if not call_sid or not raw_from or not raw_to:
        logger.warning("Twilio voice webhook: missing required fields")
        return HttpResponse(
            '<?xml version="1.0" encoding="UTF-8"?><Response><Say language="ja-JP">エラーが発生しました</Say></Response>',
            content_type="application/xml",
            status=400,
        )

    from_phone = normalize_phone(raw_from)
    to_phone = normalize_phone(raw_to)
    logger.info("Twilio voice: normalized from=%s to=%s", from_phone, to_phone)

    # to_phone → StorePhoneNumber で store 特定
    store_phone = StorePhoneNumber.objects.select_related("store").filter(phone=to_phone).first()
    if not store_phone:
        logger.warning("Twilio voice: StorePhoneNumber not found for to=%s (raw=%s)", to_phone, raw_to)
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
    call_sid = request.data.get("CallSid", "")
    call_status = request.data.get("CallStatus", "")
    raw_from = request.data.get("From", "")
    raw_to = request.data.get("To", "")

    logger.info("Twilio status webhook: CallSid=%s Status=%s From=%s To=%s", call_sid, call_status, raw_from, raw_to)

    if not call_sid:
        return HttpResponse("ok", content_type="text/plain")

    try:
        call = CallLog.objects.get(contact_id=call_sid)
    except CallLog.DoesNotExist:
        # Fallback: voice webhook で CallLog が作られなかった場合、ここで作成を試みる
        if raw_from and raw_to:
            from_phone = normalize_phone(raw_from)
            to_phone = normalize_phone(raw_to)
            store_phone = StorePhoneNumber.objects.select_related("store").filter(phone=to_phone).first()
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
                logger.warning("Twilio status fallback: StorePhoneNumber not found for to=%s", to_phone)
                return HttpResponse("ok", content_type="text/plain")
        else:
            logger.warning("Twilio status webhook: CallLog not found for %s and no From/To for fallback", call_sid)
            return HttpResponse("ok", content_type="text/plain")

    # オペレーターが既に対応完了にしている場合は上書きしない
    if call.status in (CallLog.Status.DONE,):
        return HttpResponse("ok", content_type="text/plain")

    # Twilio ステータス → Roomink ステータスへのマッピング
    if call_status in ("no-answer", "busy", "failed", "canceled"):
        call.status = CallLog.Status.MISSED
        call.save(update_fields=["status", "updated_at"])
    elif call_status == "completed" and call.status == CallLog.Status.NEW:
        # 誰も対応していないまま完了 → 不在扱い
        call.status = CallLog.Status.MISSED
        call.save(update_fields=["status", "updated_at"])

    return HttpResponse("ok", content_type="text/plain")


# ──────────────────────────────────────
# Sales
# ──────────────────────────────────────

def _parse_sales_range(request):
    """range / date_from / date_to パラメータを解析して (date_from, date_to) を返す。"""
    today = date_type.today()
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


class SalesSummaryView(APIView):
    """GET /api/op/sales-summary/?range=today|week|month or date_from&date_to"""

    def get(self, request):
        _require_manager(request)
        store = get_user_store(request)
        date_from, date_to = _parse_sales_range(request)
        if date_from is None:
            return Response(
                {"detail": "range (today/week/month) または date_from, date_to を指定してください"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(get_sales_summary(store, date_from, date_to))


class SalesExportView(APIView):
    """GET /api/op/sales-export.csv?range=..."""

    def get(self, request):
        _require_manager(request)
        store = get_user_store(request)
        date_from, date_to = _parse_sales_range(request)
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


# ──────────────────────────────────────
# Daily Settlement — manager only
# ──────────────────────────────────────

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
                f"{str(s.start_time)[:5]}-{str(s.end_time)[:5]}"
            )

        if not cast_ids:
            return Response({"date": date_str, "rows": [], "totals": {}})

        casts = {c.id: c for c in Cast.objects.filter(pk__in=cast_ids)}

        # DONE 注文
        done_orders = (
            Order.objects
            .filter(store=store, start__date=d, status=Order.Status.DONE, cast_id__in=cast_ids)
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

@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def line_webhook(request):
    """POST /api/webhook/line/ — レガシー (グローバル env) LINE webhook"""
    channel_secret = getattr(settings, "LINE_CHANNEL_SECRET", "")
    channel_token = getattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "")
    return _handle_line_webhook(request, channel_secret, channel_token)


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

class LineAlertsView(APIView):
    """GET /api/op/line-alerts/ — 当日の LINE 未連携 cast + 送信失敗を返す"""

    def get(self, request):
        store = get_user_store(request)
        today = date_type.today()

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

        return Response({
            "unlinked_casts": unlinked_list,
            "failed_notifications": failed_list,
        })


# ──────────────────────────────────────
# Store LINE設定 (manager only)
# ──────────────────────────────────────

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
