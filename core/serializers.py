from datetime import timedelta
from collections import defaultdict
from typing import List, Optional

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from .utils.phone import normalize_phone
from django.contrib.auth import get_user_model
from django.db import transaction

from .models import (
    CallLog,
    CallNote,
    Cast,
    CastAck,
    CastAdjustment,
    CastCheckoutExpenseSnapshot,
    CastDailyCheckout,
    CastExpense,
    CastExpenseTemplate,
    CastExpenseTemplateHistory,
    CastNote,
    Course,
    PointLog,
    Customer,
    Discount,
    Extension,
    Medium,
    NominationFee,
    Option,
    Order,
    OrderOption,
    Room,
    ShiftAssignment,
    ShiftConfirmNotificationLog,
    ShiftRequest,
    SmsLog,
    SmsTemplate,
    Store,
    StorePhoneNumber,
    UserProfile,
)
from .services.business_datetime import (
    BusinessDateTimeError,
    business_day_range,
    build_business_interval,
    format_business_time,
    format_extended_time,
    intervals_overlap,
)
from .services.order_availability import (
    cast_has_order_conflict,
    find_covering_shift,
)
from .services.order_policy import (
    can_modify_business_datetime,
    can_modify_order,
    is_past_business_day_order,
)

User = get_user_model()


# ──────────────────────────────────────
# Basic CRUD serializers
# ──────────────────────────────────────

class StoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Store
        fields = "__all__"


class RoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = "__all__"
        read_only_fields = ["store"]


class CastSerializer(serializers.ModelSerializer):
    line_linked = serializers.SerializerMethodField()

    class Meta:
        model = Cast
        fields = "__all__"
        read_only_fields = ["store", "line_user_id", "line_linked_at"]

    def get_line_linked(self, obj) -> bool:
        return obj.line_user_id is not None


class CustomerSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(source="store.name", read_only=True)

    class Meta:
        model = Customer
        fields = "__all__"
        read_only_fields = ["store", "user"]

    def validate_phone(self, value):
        return normalize_phone(value)


class CourseSerializer(serializers.ModelSerializer):
    target_cast_ids = serializers.PrimaryKeyRelatedField(
        source="target_casts", many=True,
        queryset=Cast.objects.all(), required=False,
    )

    class Meta:
        model = Course
        fields = ["id", "store", "name", "duration", "price", "target_cast_ids"]
        read_only_fields = ["store"]


class OptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Option
        fields = "__all__"
        read_only_fields = ["store"]


class ExtensionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Extension
        fields = "__all__"
        read_only_fields = ["store"]


class NominationFeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = NominationFee
        fields = "__all__"
        read_only_fields = ["store"]


class DiscountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Discount
        fields = "__all__"
        read_only_fields = ["store"]


class MediumSerializer(serializers.ModelSerializer):
    class Meta:
        model = Medium
        fields = "__all__"
        read_only_fields = ["store"]


class StorePhoneNumberSerializer(serializers.ModelSerializer):
    class Meta:
        model = StorePhoneNumber
        fields = "__all__"
        read_only_fields = ["store", "created_at", "updated_at"]


class PointLogSerializer(serializers.ModelSerializer):
    cast_name = serializers.CharField(source="cast.name", read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = PointLog
        fields = "__all__"
        read_only_fields = ["store", "created_by"]

    def get_created_by_name(self, obj) -> Optional[str]:
        if obj.created_by:
            return obj.created_by.username
        return None


class CastExpenseSerializer(serializers.ModelSerializer):
    cast_name = serializers.CharField(source="cast.name", read_only=True)

    class Meta:
        model = CastExpense
        fields = "__all__"
        read_only_fields = ["store"]


class CastExpenseTemplateSerializer(serializers.ModelSerializer):
    cast_name = serializers.CharField(source="cast.name", read_only=True)

    class Meta:
        model = CastExpenseTemplate
        fields = [
            "id", "store", "cast", "cast_name", "name", "amount", "memo",
            "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["store"]


class CastExpenseTemplateHistorySerializer(serializers.ModelSerializer):
    cast_name = serializers.CharField(source="cast.name", read_only=True, default=None)
    edited_by_name = serializers.SerializerMethodField()

    class Meta:
        model = CastExpenseTemplateHistory
        fields = [
            "id", "template", "cast", "cast_name", "name", "amount", "memo",
            "is_active", "action", "edited_by", "edited_by_name", "edited_at",
        ]
        read_only_fields = fields

    def get_edited_by_name(self, obj) -> Optional[str]:
        if not obj.edited_by:
            return None
        return obj.edited_by.get_full_name() or obj.edited_by.username


class CastCheckoutExpenseSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = CastCheckoutExpenseSnapshot
        fields = ["id", "template", "name", "amount", "memo"]
        read_only_fields = fields


class CastDailyCheckoutSerializer(serializers.ModelSerializer):
    """退勤提出（Phase 3-A）。cast側の提出/参照・manager側の一覧/確認で共通利用。manager_memoのみ書き込み可。"""
    cast_name = serializers.CharField(source="cast.name", read_only=True)
    reviewed_by_name = serializers.SerializerMethodField()
    expense_snapshots = CastCheckoutExpenseSnapshotSerializer(many=True, read_only=True)

    class Meta:
        model = CastDailyCheckout
        fields = [
            "id", "store", "cast", "cast_name", "date", "status",
            "done_count", "total_sales", "estimated_pay", "course_sales", "options_sales",
            "payment_fee_estimate", "net_sales_after_payment_fee",
            "actual_take_home_amount", "checklist_json", "cast_memo", "manager_memo",
            "submitted_at", "reviewed_at", "reviewed_by", "reviewed_by_name",
            "expense_snapshots", "created_at", "updated_at",
        ]
        read_only_fields = [f for f in fields if f != "manager_memo"]

    def get_reviewed_by_name(self, obj) -> Optional[str]:
        return obj.reviewed_by.username if obj.reviewed_by else None


class CastAdjustmentSerializer(serializers.ModelSerializer):
    """調整金台帳（Phase 3-E）manager側 CRUD 用。status/resolved_* は resolve/void アクション経由でのみ変更する。"""
    cast_name = serializers.CharField(source="cast.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    source_type_display = serializers.CharField(source="get_source_type_display", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    resolved_by_name = serializers.SerializerMethodField()

    class Meta:
        model = CastAdjustment
        fields = [
            "id", "store", "cast", "cast_name", "date", "amount", "title", "memo",
            "status", "status_display", "source_type", "source_type_display",
            "source_checkout", "source_order",
            "created_by", "created_by_name", "created_at", "updated_at",
            "resolved_by", "resolved_by_name", "resolved_at", "resolved_memo",
        ]
        read_only_fields = [
            "store", "status",
            "created_by", "created_at", "updated_at",
            "resolved_by", "resolved_at", "resolved_memo",
        ]

    def get_created_by_name(self, obj) -> Optional[str]:
        return obj.created_by.username if obj.created_by else None

    def get_resolved_by_name(self, obj) -> Optional[str]:
        return obj.resolved_by.username if obj.resolved_by else None


class CastAdjustmentCastSerializer(serializers.ModelSerializer):
    """調整金台帳 cast本人閲覧用。作成/編集/解消は不可（全項目read-only）。"""
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = CastAdjustment
        fields = [
            "id", "date", "amount", "title", "memo",
            "status", "status_display", "resolved_at", "created_at",
        ]
        read_only_fields = fields


class CastNoteSerializer(serializers.ModelSerializer):
    """ノート/施術マニュアル（manager側 CRUD 用）。既存のRoomink操作マニュアル機能とは別物。"""
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    visibility_display = serializers.CharField(source="get_visibility_display", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    updated_by_name = serializers.SerializerMethodField()

    class Meta:
        model = CastNote
        fields = [
            "id", "store", "title", "category", "body", "status", "status_display",
            "is_pinned", "visibility", "visibility_display", "video_url",
            "created_by", "created_by_name", "updated_by", "updated_by_name",
            "published_at", "created_at", "updated_at",
        ]
        read_only_fields = ["store", "created_by", "updated_by", "published_at", "created_at", "updated_at"]

    def get_created_by_name(self, obj) -> Optional[str]:
        return obj.created_by.username if obj.created_by else None

    def get_updated_by_name(self, obj) -> Optional[str]:
        return obj.updated_by.username if obj.updated_by else None


class CastNoteCastSerializer(serializers.ModelSerializer):
    """ノート/施術マニュアル cast本人閲覧用。読み取り専用。"""
    category_label = serializers.CharField(source="category", read_only=True)

    class Meta:
        model = CastNote
        fields = [
            "id", "title", "category", "category_label", "body",
            "is_pinned", "video_url", "published_at",
        ]
        read_only_fields = fields


class ShiftConfirmNotificationLogSerializer(serializers.ModelSerializer):
    """出勤確認外部通知ログ（土台）。manager/staff閲覧用。実送信は行わない。"""
    cast_name = serializers.CharField(source="cast.name", read_only=True)
    alert_level_display = serializers.CharField(source="get_alert_level_display", read_only=True)
    target_type_display = serializers.CharField(source="get_target_type_display", read_only=True)
    channel_display = serializers.CharField(source="get_channel_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ShiftConfirmNotificationLog
        fields = [
            "id", "store", "shift_assignment", "cast", "cast_name",
            "alert_level", "alert_level_display", "target_type", "target_type_display",
            "channel", "channel_display", "status", "status_display",
            "message", "error_message", "sent_at", "created_by", "created_by_name", "created_at",
        ]
        read_only_fields = fields

    def get_created_by_name(self, obj) -> Optional[str]:
        return obj.created_by.username if obj.created_by else None


class StaffSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = UserProfile
        fields = ["id", "username", "email", "role", "avatar_url", "store"]
        read_only_fields = ["store"]


class StaffCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=128, write_only=True)
    email = serializers.EmailField(required=False, default="")
    role = serializers.ChoiceField(
        choices=[("staff", "スタッフ"), ("manager", "マネージャー")],
        default="staff",
    )
    avatar_url = serializers.URLField(required=False, default="")

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("このユーザー名は既に使用されています")
        return value

    def create(self, validated_data):
        from .services.cast_user import create_staff_with_user
        store = validated_data.pop("store")
        profile = create_staff_with_user(
            store=store,
            username=validated_data["username"],
            password=validated_data["password"],
            email=validated_data.get("email", ""),
            role=validated_data.pop("role", "staff"),
            avatar_url=validated_data.pop("avatar_url", ""),
        )
        return profile


class StaffUpdateSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    role = serializers.ChoiceField(
        choices=[("staff", "スタッフ"), ("manager", "マネージャー")],
        required=False,
    )
    avatar_url = serializers.URLField(required=False, allow_blank=True)
    password = serializers.CharField(max_length=128, write_only=True, required=False)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        email = validated_data.pop("email", None)
        if "role" in validated_data:
            instance.role = validated_data["role"]
        if "avatar_url" in validated_data:
            instance.avatar_url = validated_data["avatar_url"]
        instance.save()
        if email is not None:
            instance.user.email = email
            instance.user.save(update_fields=["email"])
        if password:
            instance.user.set_password(password)
            instance.user.save(update_fields=["password"])
        return instance


# ──────────────────────────────────────
# ShiftAssignment (with overlap guard)
# ──────────────────────────────────────

class ShiftAssignmentSerializer(serializers.ModelSerializer):
    cast_name = serializers.CharField(source="cast.name", read_only=True)
    cast_avatar_url = serializers.CharField(source="cast.avatar_url", read_only=True)
    room_name = serializers.CharField(source="room.name", read_only=True)
    end_time_extended = serializers.SerializerMethodField()

    class Meta:
        model = ShiftAssignment
        fields = "__all__"
        read_only_fields = ["store"]

    def validate(self, data):
        # store は read_only のため新規作成時は data に載らない。
        # ViewSet / 週次入力から context 経由で受け取り、重複チェックを店舗内に限定する。
        store = (
            data.get("store")
            or getattr(self.instance, "store", None)
            or self.context.get("store")
        )
        date = data.get("date", getattr(self.instance, "date", None))
        cast = data.get("cast", getattr(self.instance, "cast", None))
        start_time = data.get("start_time", getattr(self.instance, "start_time", None))
        end_time = data.get("end_time", getattr(self.instance, "end_time", None))
        end_day_offset = data.get(
            "end_day_offset",
            getattr(self.instance, "end_day_offset", 0),
        )

        start_at = end_at = None
        if date and start_time and end_time:
            try:
                format_extended_time(end_time, end_day_offset)
                start_at, end_at = build_business_interval(
                    date,
                    start_time,
                    end_time,
                    end_day_offset=end_day_offset,
                    timezone_name=store.timezone if store else "Asia/Tokyo",
                )
            except BusinessDateTimeError as exc:
                raise serializers.ValidationError(str(exc)) from exc

        room = data.get("room", getattr(self.instance, "room", None))
        if store is not None:
            if cast is not None and cast.store_id != store.id:
                raise serializers.ValidationError("他店舗のキャストは指定できません")
            if room is not None and room.store_id != store.id:
                raise serializers.ValidationError("他店舗のルームは指定できません")

        if store and cast and date and start_at and end_at:
            qs = ShiftAssignment.objects.filter(
                store=store,
                cast=cast,
                date__range=(date - timedelta(days=1), date + timedelta(days=1)),
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            for existing in qs:
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
                if intervals_overlap(start_at, end_at, existing_start, existing_end):
                    raise serializers.ValidationError(
                        "このキャストの既存シフトと時間が重複しています"
                    )

        return data

    def get_end_time_extended(self, obj) -> str:
        return format_extended_time(obj.end_time, obj.end_day_offset)


# ──────────────────────────────────────
# ShiftRequest
# ──────────────────────────────────────

class CastShiftRequestSerializer(serializers.ModelSerializer):
    cast_name = serializers.CharField(source="cast.name", read_only=True)
    desired_room_name = serializers.CharField(source="desired_room.name", read_only=True, default=None)
    approved_room_name = serializers.CharField(source="approved_room.name", read_only=True, default=None)
    decided_by_name = serializers.SerializerMethodField()
    end_time_extended = serializers.SerializerMethodField()
    approved_end_time_extended = serializers.SerializerMethodField()

    class Meta:
        model = ShiftRequest
        fields = "__all__"
        # cast本人は申請内容のみ編集可。承認/却下に関するフィールドは閲覧専用にする。
        read_only_fields = [
            "store", "cast", "status", "admin_memo",
            "approved_date", "approved_start_time", "approved_end_time",
            "approved_end_day_offset", "approved_room",
            "decided_at", "decided_by",
        ]

    def get_decided_by_name(self, obj) -> Optional[str]:
        if not obj.decided_by:
            return None
        return obj.decided_by.get_full_name() or obj.decided_by.username

    def validate(self, data):
        request = self.context.get("request")
        start_time = data.get("start_time", getattr(self.instance, "start_time", None))
        end_time = data.get("end_time", getattr(self.instance, "end_time", None))
        end_day_offset = data.get(
            "end_day_offset",
            getattr(self.instance, "end_day_offset", 0),
        )

        # 同一キャスト・同一時間帯の REQUESTED 重複チェック
        cast = (
            data.get("cast")
            or getattr(self.instance, "cast", None)
            or getattr(getattr(request, "user", None), "cast_profile", None)
        )
        date = data.get("date", getattr(self.instance, "date", None))
        start_at = end_at = None
        if cast and date and start_time and end_time:
            try:
                format_extended_time(end_time, end_day_offset)
                start_at, end_at = build_business_interval(
                    date,
                    start_time,
                    end_time,
                    end_day_offset=end_day_offset,
                    timezone_name=cast.store.timezone,
                )
            except BusinessDateTimeError as exc:
                raise serializers.ValidationError(str(exc)) from exc

            qs = ShiftRequest.objects.filter(
                cast=cast,
                date__range=(date - timedelta(days=1), date + timedelta(days=1)),
                status=ShiftRequest.Status.REQUESTED,
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            for existing in qs:
                try:
                    existing_start, existing_end = build_business_interval(
                        existing.date,
                        existing.start_time,
                        existing.end_time,
                        end_day_offset=existing.end_day_offset,
                        timezone_name=cast.store.timezone,
                    )
                except BusinessDateTimeError:
                    continue
                if intervals_overlap(start_at, end_at, existing_start, existing_end):
                    raise serializers.ValidationError("同じ時間帯に申請中のシフトがあります")

        return data

    def get_end_time_extended(self, obj) -> str:
        return format_extended_time(obj.end_time, obj.end_day_offset)

    def get_approved_end_time_extended(self, obj) -> Optional[str]:
        if obj.approved_end_time is None:
            return None
        return format_extended_time(
            obj.approved_end_time,
            obj.approved_end_day_offset,
        )


class OpShiftRequestSerializer(serializers.ModelSerializer):
    cast_name = serializers.CharField(source="cast.name", read_only=True)
    desired_room_name = serializers.CharField(source="desired_room.name", read_only=True, default=None)
    approved_room_name = serializers.CharField(source="approved_room.name", read_only=True, default=None)
    decided_by_name = serializers.SerializerMethodField()
    end_time_extended = serializers.SerializerMethodField()
    approved_end_time_extended = serializers.SerializerMethodField()

    class Meta:
        model = ShiftRequest
        fields = "__all__"
        read_only_fields = [
            "store", "cast",
            "approved_date", "approved_start_time", "approved_end_time",
            "approved_end_day_offset", "approved_room",
            "decided_at", "decided_by",
        ]

    def get_decided_by_name(self, obj) -> Optional[str]:
        if not obj.decided_by:
            return None
        return obj.decided_by.get_full_name() or obj.decided_by.username

    def get_end_time_extended(self, obj) -> str:
        return format_extended_time(obj.end_time, obj.end_day_offset)

    def get_approved_end_time_extended(self, obj) -> Optional[str]:
        if obj.approved_end_time is None:
            return None
        return format_extended_time(
            obj.approved_end_time,
            obj.approved_end_day_offset,
        )


# ──────────────────────────────────────
# Order — read
# ──────────────────────────────────────

def build_customer_label(customer):
    name = customer.display_name or customer.phone
    if customer.flag == Customer.Flag.BAN:
        ban_label = customer.get_ban_type_display() if customer.ban_type and customer.ban_type != Customer.BanType.NONE else "出禁"
        return f"{name} ★{ban_label}"
    if customer.flag == Customer.Flag.ATTENTION:
        return f"{name} ★注意"
    return name


class OrderSerializer(serializers.ModelSerializer):
    customer_label = serializers.SerializerMethodField()
    options = serializers.SerializerMethodField()
    option_ids = serializers.SerializerMethodField()
    is_unconfirmed = serializers.SerializerMethodField()
    is_past_business_day = serializers.SerializerMethodField()
    can_modify = serializers.SerializerMethodField()
    cast_name = serializers.CharField(source="cast.name", read_only=True)
    room_name = serializers.CharField(source="room.name", read_only=True)
    # course_name is now a snapshot field on Order; no source override needed

    class Meta:
        model = Order
        fields = [
            "id", "store", "cast", "room", "customer", "course",
            "cast_name", "room_name", "course_name", "customer_label",
            "start", "end", "status", "options", "option_ids", "is_unconfirmed",
            "is_past_business_day", "can_modify", "memo",
            "course_price", "options_price",
            "extension", "extension_name", "extension_price",
            "nomination_fee", "nomination_fee_name", "nomination_fee_price",
            "discount", "discount_name", "discount_type_snapshot", "discount_value_snapshot", "discount_amount",
            "medium", "medium_name",
            "total_price", "payment_method",
            "created_at", "updated_at",
        ]

    def get_customer_label(self, obj) -> str:
        return build_customer_label(obj.customer)

    def get_options(self, obj) -> List[str]:
        # prefetch_related 済みの場合 DB クエリを避ける
        if hasattr(obj, '_prefetched_objects_cache') and 'options' in obj._prefetched_objects_cache:
            return [o.name for o in obj.options.all()]
        return list(obj.options.values_list("name", flat=True))

    def get_option_ids(self, obj) -> List[int]:
        return list(obj.options.values_list("id", flat=True))

    def get_is_unconfirmed(self, obj) -> bool:
        return not CastAck.objects.filter(order=obj, acked_at__isnull=False).exists()

    def get_is_past_business_day(self, obj) -> bool:
        return is_past_business_day_order(obj)

    def get_can_modify(self, obj) -> bool:
        request = self.context.get("request")
        return can_modify_order(request.user if request else None, obj)


# ──────────────────────────────────────
# Order — create
# ──────────────────────────────────────

class OrderCreateSerializer(serializers.ModelSerializer):
    options = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Option.objects.all(), required=False,
    )
    medium = serializers.PrimaryKeyRelatedField(
        queryset=Medium.objects.all(), required=False, allow_null=True,
    )
    discount = serializers.PrimaryKeyRelatedField(
        queryset=Discount.objects.all(), required=False, allow_null=True,
    )
    extension = serializers.PrimaryKeyRelatedField(
        queryset=Extension.objects.all(), required=False, allow_null=True,
    )

    class Meta:
        model = Order
        fields = [
            "cast", "customer", "course", "start", "end",
            "memo", "options", "extension", "medium", "discount", "payment_method",
        ]
        extra_kwargs = {
            "end": {"required": False},
            "memo": {"required": False, "default": ""},
            "payment_method": {"required": False},
        }

    def validate(self, data):
        store = data["customer"].store
        data["store"] = store

        request = self.context.get("request")
        if request and not can_modify_business_datetime(
            request.user,
            data["start"],
            store,
        ):
            raise PermissionDenied(
                "過去営業日の予約を作成できるのはマネージャーのみです。"
            )

        # A) BAN check
        customer = data["customer"]
        if customer.flag == Customer.Flag.BAN:
            raise serializers.ValidationError("このお客様は予約を受け付けられません")

        extension = data.get("extension")
        if extension is not None:
            if extension.store_id != store.id:
                raise serializers.ValidationError({"extension": "他店舗の延長は使用できません"})
            if not extension.is_active:
                raise serializers.ValidationError({"extension": "無効な延長は使用できません"})

        # B) end auto-calc（延長選択時は終了時刻へ必ず反映）
        course = data["course"]
        if extension is not None:
            data["end"] = data["start"] + timedelta(
                minutes=course.duration + extension.duration,
            )
        elif not data.get("end"):
            data["end"] = data["start"] + timedelta(minutes=course.duration)
        if data["end"] <= data["start"]:
            raise serializers.ValidationError("終了時刻は開始時刻より後にしてください")

        # C) ShiftAssignment → room
        start = data["start"]
        end = data["end"]
        assignment = find_covering_shift(store, data["cast"], start, end)
        if assignment is None:
            raise serializers.ValidationError("このキャストは指定日時にシフトがありません（または当欠）")
        data["room"] = assignment.room

        # D) cast conflict (既存予約の end + interval_minutes をインターバル占有終端とみなす)
        cast_obj = data["cast"]
        if cast_has_order_conflict(cast_obj, start, end):
            raise serializers.ValidationError(
                "このキャストは指定時間に予約が入っています（インターバル含む）"
            )

        # E) room conflict
        if Order.objects.filter(
            room=data["room"],
            status__in=Order.ACTIVE_STATUSES,
            start__lt=end,
            end__gt=start,
        ).exists():
            raise serializers.ValidationError("指定ルームは使用中です")

        # F) discount cross-store check
        discount = data.get("discount")
        if discount is not None and discount.store_id != store.id:
            raise serializers.ValidationError("他店舗の割引は使用できません")

        return data

    def create(self, validated_data):
        from .services.pricing import recalculate_order_total
        with transaction.atomic():
            option_objs = validated_data.pop("options", [])
            course = validated_data["course"]
            validated_data["course_name"] = course.name
            validated_data["course_price"] = course.price
            opts_total = sum(o.price for o in option_objs)
            validated_data["options_price"] = opts_total
            extension = validated_data.get("extension")
            if extension:
                validated_data["extension_name"] = extension.name
                validated_data["extension_price"] = extension.price
            medium = validated_data.get("medium")
            if medium:
                validated_data["medium_name"] = medium.name
            discount = validated_data.get("discount")
            if discount:
                validated_data["discount_name"] = discount.name
                validated_data["discount_type_snapshot"] = discount.discount_type
                validated_data["discount_value_snapshot"] = discount.value
            order = Order.objects.create(**validated_data)
            for opt in option_objs:
                OrderOption.objects.get_or_create(order=order, option=opt)
            recalculate_order_total(order)
        return order

    def to_representation(self, instance):
        return OrderSerializer(instance, context=self.context).data


# ──────────────────────────────────────
# Order — update (partial)
# ──────────────────────────────────────

class OrderUpdateSerializer(serializers.ModelSerializer):
    options = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Option.objects.all(), required=False,
    )

    class Meta:
        model = Order
        fields = ["cast", "course", "start", "end", "memo", "options", "payment_method"]

    def validate(self, data):
        instance = self.instance
        cast = data.get("cast", instance.cast)
        start = data.get("start", instance.start)
        end = data.get("end", instance.end)

        request = self.context.get("request")
        if request and not can_modify_business_datetime(
            request.user,
            start,
            instance.store,
        ):
            raise PermissionDenied(
                "過去営業日の予約へ変更できるのはマネージャーのみです。"
            )

        # course changed → recalc end if not explicitly set
        if "course" in data and "end" not in data:
            end = start + timedelta(minutes=data["course"].duration)
            data["end"] = end

        if end <= start:
            raise serializers.ValidationError("終了時刻は開始時刻より後にしてください")

        time_or_cast_changed = "cast" in data or "start" in data or "end" in data
        if time_or_cast_changed:
            store = instance.store

            # ShiftAssignment → room auto-assign
            assignment = find_covering_shift(store, cast, start, end)
            if assignment is None:
                raise serializers.ValidationError("このキャストは指定日時にシフトがありません（または当欠）")
            data["room"] = assignment.room

            # Cast conflict (exclude self, インターバル考慮)
            if cast_has_order_conflict(
                cast,
                start,
                end,
                exclude_order_id=instance.pk,
            ):
                raise serializers.ValidationError(
                    "このキャストは指定時間に予約が入っています（インターバル含む）"
                )

            # Room conflict (exclude self)
            if Order.objects.filter(
                room=data["room"],
                status__in=Order.ACTIVE_STATUSES,
                start__lt=end,
                end__gt=start,
            ).exclude(pk=instance.pk).exists():
                raise serializers.ValidationError("指定ルームは使用中です")

        return data

    def update(self, instance, validated_data):
        option_objs = validated_data.pop("options", None)

        # course snapshot
        if "course" in validated_data:
            course = validated_data["course"]
            validated_data["course_name"] = course.name
            validated_data["course_price"] = course.price

        instance = super().update(instance, validated_data)

        # options
        if option_objs is not None:
            OrderOption.objects.filter(order=instance).delete()
            for opt in option_objs:
                OrderOption.objects.create(order=instance, option=opt)
            instance.options_price = sum(o.price for o in option_objs)

        # recalc total
        from .services.pricing import recalculate_order_total
        recalculate_order_total(instance)
        instance.save()

        return instance

    def to_representation(self, instance):
        return OrderSerializer(instance, context=self.context).data


# ──────────────────────────────────────
# Schedule API serializers
# ──────────────────────────────────────

# ──────────────────────────────────────
# Cast Today API serializer
# ──────────────────────────────────────

class CastTodayOrderSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    start_time_extended = serializers.CharField()
    end_time_extended = serializers.CharField()
    status = serializers.CharField()
    room_id = serializers.IntegerField()
    room_name = serializers.CharField()
    customer_label = serializers.CharField()
    course_name = serializers.CharField()
    course_price = serializers.IntegerField()
    memo = serializers.CharField()
    is_unconfirmed = serializers.BooleanField()


# ──────────────────────────────────────
# Schedule API serializers
# ──────────────────────────────────────

class ScheduleShiftSerializer(serializers.ModelSerializer):
    room_name = serializers.CharField(source="room.name", read_only=True)
    room_color = serializers.CharField(source="room.background_color", read_only=True, default="")
    end_time_extended = serializers.SerializerMethodField()

    class Meta:
        model = ShiftAssignment
        fields = [
            "id", "room_id", "room_name", "room_color",
            "start_time", "end_time", "end_day_offset", "end_time_extended",
            "clocked_in_at", "confirmed_at",
            "daily_memo", "is_absent",
        ]

    def get_end_time_extended(self, obj) -> str:
        return format_extended_time(obj.end_time, obj.end_day_offset)


class ScheduleCastSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    avatar_url = serializers.CharField()
    interval_minutes = serializers.IntegerField()
    staff_memo = serializers.CharField(allow_blank=True, required=False)
    shifts = ScheduleShiftSerializer(many=True)


class ScheduleOrderSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    cast_id = serializers.IntegerField()
    room_id = serializers.IntegerField()
    customer_label = serializers.CharField()
    course_name = serializers.CharField()
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    start_time_extended = serializers.CharField()
    end_time_extended = serializers.CharField()
    status = serializers.CharField()
    options = serializers.ListField(child=serializers.CharField())
    is_unconfirmed = serializers.BooleanField()


class ScheduleKpiSerializer(serializers.Serializer):
    total_orders = serializers.IntegerField()
    confirmed = serializers.IntegerField()
    requested = serializers.IntegerField()
    estimated_sales = serializers.IntegerField()


class ScheduleResponseSerializer(serializers.Serializer):
    date = serializers.DateField()
    store_id = serializers.IntegerField()
    casts = ScheduleCastSerializer(many=True)
    orders = ScheduleOrderSerializer(many=True)
    kpi = ScheduleKpiSerializer()


def build_schedule_data(store, date):
    shifts = (
        ShiftAssignment.objects
        .filter(store=store, date=date)
        .select_related("room", "cast")
    )

    shifts_by_cast = defaultdict(list)
    for s in shifts:
        shifts_by_cast[s.cast_id].append(s)

    cast_ids_with_shift = set(shifts_by_cast.keys())
    casts = Cast.objects.filter(store=store, pk__in=cast_ids_with_shift).order_by("name")

    # タイムライン表示順: display_order（1〜）が設定されたキャストを先頭に、
    # 未設定（0）は従来どおり名前順で後ろに並べる。
    def _cast_sort_key(c):
        orders_set = [
            s.display_order for s in shifts_by_cast.get(c.id, []) if s.display_order
        ]
        if orders_set:
            return (0, min(orders_set), c.name)
        return (1, 0, c.name)

    casts = sorted(casts, key=_cast_sort_key)

    cast_data = []
    for c in casts:
        cast_data.append({
            "id": c.id,
            "name": c.name,
            "avatar_url": c.avatar_url,
            "interval_minutes": c.interval_minutes,
            "staff_memo": c.staff_memo or "",
            "shifts": shifts_by_cast.get(c.id, []),
        })

    range_start, range_end = business_day_range(date, store.timezone)
    orders = (
        Order.objects
        .filter(store=store, start__gte=range_start, start__lt=range_end)
        .select_related("customer", "course")
        .prefetch_related("options")
    )

    # CastAck lookup for is_unconfirmed
    acked_order_ids = set(
        CastAck.objects
        .filter(order__in=orders, acked_at__isnull=False)
        .values_list("order_id", flat=True)
    )

    order_data = []
    for o in orders:
        order_data.append({
            "id": o.id,
            "cast_id": o.cast_id,
            "room_id": o.room_id,
            "customer_label": build_customer_label(o.customer),
            "course_name": o.course_name,
            "start": o.start,
            "end": o.end,
            "start_time_extended": format_business_time(o.start, date, store.timezone),
            "end_time_extended": format_business_time(o.end, date, store.timezone),
            "status": o.status,
            "options": [opt.name for opt in o.options.all()],
            "is_unconfirmed": o.id not in acked_order_ids,
        })

    # orders は既に評価済み（上の for o in orders で）なので list 化して再利用
    orders_list = list(orders)
    done_orders = [o for o in orders_list if o.status == Order.Status.DONE]
    estimated_sales = sum(o.total_price for o in done_orders)

    kpi = {
        "total_orders": len(orders_list),
        "confirmed": sum(1 for o in orders_list if o.status == Order.Status.CONFIRMED),
        "requested": sum(1 for o in orders_list if o.status == Order.Status.REQUESTED),
        "estimated_sales": estimated_sales,
    }

    return {
        "date": date,
        "store_id": store.id,
        "casts": cast_data,
        "orders": order_data,
        "kpi": kpi,
    }


def build_room_schedule_data(store, date):
    rooms = Room.objects.filter(store=store).order_by("sort_order")

    range_start, range_end = business_day_range(date, store.timezone)
    orders = (
        Order.objects
        .filter(
            store=store,
            start__gte=range_start,
            start__lt=range_end,
            room__isnull=False,
        )
        .select_related("customer", "course", "cast")
        .prefetch_related("options")
    )

    acked_order_ids = set(
        CastAck.objects
        .filter(order__in=orders, acked_at__isnull=False)
        .values_list("order_id", flat=True)
    )

    order_data = []
    for o in orders:
        order_data.append({
            "id": o.id,
            "room_id": o.room_id,
            "cast_name": o.cast.name if o.cast else "",
            "customer_label": build_customer_label(o.customer),
            "course_name": o.course_name,
            "start": o.start,
            "end": o.end,
            "start_time_extended": format_business_time(o.start, date, store.timezone),
            "end_time_extended": format_business_time(o.end, date, store.timezone),
            "status": o.status,
            "options": [opt.name for opt in o.options.all()],
            "is_unconfirmed": o.id not in acked_order_ids,
        })

    orders_list = list(orders)
    done_orders = [o for o in orders_list if o.status == Order.Status.DONE]
    estimated_sales = sum(o.total_price for o in done_orders)

    kpi = {
        "total_orders": len(orders_list),
        "confirmed": sum(1 for o in orders_list if o.status == Order.Status.CONFIRMED),
        "requested": sum(1 for o in orders_list if o.status == Order.Status.REQUESTED),
        "estimated_sales": estimated_sales,
    }

    return {
        "date": date,
        "store_id": store.id,
        "rooms": [{
            "id": r.id,
            "name": r.name,
            "sort_order": r.sort_order,
            "background_color": r.background_color,
        } for r in rooms],
        "orders": order_data,
        "kpi": kpi,
    }


# ──────────────────────────────────────
# CallLog / CallNote (Phase 3-A: op 手動架電履歴)
# ──────────────────────────────────────

class CallNoteSerializer(serializers.ModelSerializer):
    author_label = serializers.SerializerMethodField()

    class Meta:
        model = CallNote
        fields = ["id", "body", "author", "author_label", "created_at"]
        read_only_fields = ["author", "created_at"]

    def get_author_label(self, obj) -> str:
        if not obj.author_id:
            return ""
        u = obj.author
        return u.get_full_name() or u.username


class CallLogSerializer(serializers.ModelSerializer):
    customer_label = serializers.SerializerMethodField()
    assigned_to_label = serializers.SerializerMethodField()
    notes = CallNoteSerializer(many=True, read_only=True)

    class Meta:
        model = CallLog
        fields = [
            "id", "contact_id", "from_phone", "to_phone", "status",
            "customer", "customer_label",
            "assigned_to", "assigned_to_label",
            "is_repeat", "created_at", "updated_at",
            "notes",
        ]
        read_only_fields = [
            "id", "contact_id", "status", "assigned_to", "is_repeat",
            "created_at", "updated_at",
        ]

    def get_customer_label(self, obj) -> str:
        if not obj.customer_id:
            return ""
        return build_customer_label(obj.customer)

    def get_assigned_to_label(self, obj) -> str:
        if not obj.assigned_to_id:
            return ""
        u = obj.assigned_to
        return u.get_full_name() or u.username


# ──────────────────────────────────────
# SMS（文面テンプレート / 送信履歴）
# ──────────────────────────────────────

class SmsTemplateSerializer(serializers.ModelSerializer):
    payment_method_label = serializers.CharField(source="get_payment_method_display", read_only=True)
    updated_by_name = serializers.SerializerMethodField()

    class Meta:
        model = SmsTemplate
        fields = [
            "id", "template_type", "payment_method", "payment_method_label",
            "body", "is_active", "updated_by_name", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_updated_by_name(self, obj) -> str:
        if not obj.updated_by_id:
            return ""
        u = obj.updated_by
        return u.get_full_name() or u.username


class SmsLogSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    template_type_label = serializers.CharField(source="get_template_type_display", read_only=True)
    payment_method_label = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = SmsLog
        fields = [
            "id", "order", "to_phone", "body", "status", "status_label",
            "template_type", "template_type_label", "payment_method", "payment_method_label",
            "provider", "provider_message_id", "error_message",
            "created_by_name", "sent_at",
        ]

    def get_payment_method_label(self, obj) -> str:
        if not obj.payment_method:
            return ""
        return dict(Order.PaymentMethod.choices).get(obj.payment_method, obj.payment_method)

    def get_created_by_name(self, obj) -> str:
        if not obj.created_by_id:
            return ""
        u = obj.created_by
        return u.get_full_name() or u.username
