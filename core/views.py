import csv
import io
import os
from datetime import date as date_type, timedelta

from django.contrib.auth import authenticate, login, logout
from django.views.decorators.csrf import ensure_csrf_cookie
from django.db import transaction
from django.db.models import ProtectedError
from django.utils import timezone
from rest_framework import parsers, viewsets, status
from rest_framework.decorators import action, api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    CallLog, CallNote, Cast, CastAck, Course, Customer, Discount, Extension, Medium, NominationFee, Option, Order, OrderOption,
    Room, ShiftAssignment, ShiftRequest, Store, StorePhoneNumber,
)
from .serializers import (
    CastSerializer,
    CastShiftRequestSerializer,
    CastTodayOrderSerializer,
    CourseSerializer,
    CustomerSerializer,
    DiscountSerializer,
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
from .services.customer_context import resolve_customer
from .services.pricing import recalculate_order_total
from .services.notify import (
    notify_cast_order,
    notify_order_cancelled,
    notify_order_confirmed,
)


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
    return Response({
        "id": request.user.id,
        "username": request.user.username,
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

        store = Store.objects.first()
        if store is None:
            return Response(
                {"detail": "店舗が登録されていません"},
                status=status.HTTP_400_BAD_REQUEST,
            )

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

        store = Store.objects.first()
        if store is None:
            return Response(
                {"detail": "店舗が登録されていません"},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
        extension_id = request.data.get("extension_id")

        if extension_id is None:
            # 解除
            order.extension = None
            order.extension_name = ""
            order.extension_price = 0
        else:
            try:
                ext = Extension.objects.get(pk=extension_id)
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
        nomination_fee_id = request.data.get("nomination_fee_id")

        if nomination_fee_id is None:
            order.nomination_fee = None
            order.nomination_fee_name = ""
            order.nomination_fee_price = 0
        else:
            try:
                nf = NominationFee.objects.get(pk=nomination_fee_id)
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
        discount_id = request.data.get("discount_id")

        if discount_id is None:
            order.discount = None
            order.discount_name = ""
            order.discount_type_snapshot = ""
            order.discount_value_snapshot = 0
            order.discount_amount = 0
        else:
            try:
                dc = Discount.objects.get(pk=discount_id)
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
        medium_id = request.data.get("medium_id")

        if medium_id is None:
            order.medium = None
            order.medium_name = ""
        else:
            try:
                med = Medium.objects.get(pk=medium_id)
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

    store = Store.objects.first()
    if store is None:
        return Response(
            {"detail": "店舗が登録されていません"},
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
            {"id": c.id, "name": c.name, "avatar_url": c.avatar_url}
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

        # 既存予約取得（CANCELLED以外）
        orders = Order.objects.filter(
            cast=cast,
            start__date=d,
            status__in=Order.ACTIVE_STATUSES,
        )
        busy = [(o.start.time(), o.end.time()) for o in orders]

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
        casts = [{"id": c.id, "name": c.name, "avatar_url": c.avatar_url} for c in Cast.objects.filter(store=store).order_by("name")]
        courses = [{"id": c.id, "name": c.name, "duration": c.duration, "price": c.price} for c in Course.objects.filter(store=store).order_by("id")]
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

    def perform_create(self, serializer):
        store = Store.objects.order_by("id").first()
        if store is None:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"store": "店舗が登録されていません"})
        serializer.save(store=store)


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

    def perform_create(self, serializer):
        store = Store.objects.order_by("id").first()
        if store is None:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"store": "店舗が登録されていません"})
        serializer.save(store=store)


class CastViewSet(viewsets.ModelViewSet):
    queryset = Cast.objects.order_by("name")
    serializer_class = CastSerializer

    def perform_create(self, serializer):
        store = Store.objects.order_by("id").first()
        if store is None:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"store": "店舗が登録されていません"})
        serializer.save(store=store)

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


class CourseViewSet(viewsets.ModelViewSet):
    queryset = Course.objects.order_by("id")
    serializer_class = CourseSerializer

    def perform_create(self, serializer):
        store = Store.objects.order_by("id").first()
        if store is None:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"store": "店舗が登録されていません"})
        serializer.save(store=store)

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

    def perform_create(self, serializer):
        store = Store.objects.order_by("id").first()
        if store is None:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"store": "店舗が登録されていません"})
        serializer.save(store=store)

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

    def perform_create(self, serializer):
        store = Store.objects.order_by("id").first()
        if store is None:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"store": "店舗が登録されていません"})
        serializer.save(store=store)

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

    def perform_create(self, serializer):
        store = Store.objects.order_by("id").first()
        if store is None:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"store": "店舗が登録されていません"})
        serializer.save(store=store)

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

    def perform_create(self, serializer):
        store = Store.objects.order_by("id").first()
        if store is None:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"store": "店舗が登録されていません"})
        serializer.save(store=store)

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

    def perform_create(self, serializer):
        store = Store.objects.order_by("id").first()
        if store is None:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"store": "店舗が登録されていません"})
        serializer.save(store=store)

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

    def perform_create(self, serializer):
        store = Store.objects.order_by("id").first()
        if store is None:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"store": "店舗が登録されていません"})
        serializer.save(store=store)

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

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        obj = self.get_object()
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
            room = Room.objects.get(pk=room_id)
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
            obj, is_new = Cast.objects.update_or_create(
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

        store = Store.objects.first()
        if store is None:
            return Response(
                {"detail": "店舗が登録されていません"},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
        calls = (
            CallLog.objects
            .filter(status__in=[CallLog.Status.NEW, CallLog.Status.IN_PROGRESS])
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
