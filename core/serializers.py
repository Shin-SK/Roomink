import re
from datetime import date as date_type, datetime, timedelta
from collections import defaultdict
from typing import List, Optional
from zoneinfo import ZoneInfo

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from drf_spectacular.utils import extend_schema_field

from .utils.phone import normalize_phone
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.db import transaction

from .security import validate_password_for_role
from .store_access import get_request_profile, get_user_store

from .models import (
    Area,
    CallLog,
    CallNote,
    Cast,
    CastAreaPreference,
    CastUnavailableTime,
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
    OrderAccountingCorrection,
    Room,
    ShiftAssignment,
    ShiftConfirmNotificationLog,
    ShiftRequest,
    SmsLog,
    SmsTemplate,
    Store,
    StoreMembership,
    StorePhoneNumber,
    UserProfile,
    normalize_area_name,
)
from .services.business_datetime import (
    BusinessDateTimeError,
    business_date_for_datetime,
    business_day_range,
    build_business_interval,
    build_store_datetime,
    format_business_time,
    format_extended_time,
    intervals_overlap,
    parse_extended_time,
)
from .services.order_availability import (
    cast_has_order_conflict,
    cast_has_unavailable_time_conflict,
    find_covering_shift,
)
from .services.room_assignment import suggest_room_for_shift
from .services.order_policy import (
    can_modify_business_datetime,
    can_modify_order,
    is_past_business_day_order,
)
from .services.daily_settlement_lock import is_daily_settlement_locked
from .services.order_editing import require_current_order, order_edit_snapshot, record_order_edit

User = get_user_model()

MAX_EXTENSION_DURATION_MINUTES = 180


def validate_extension_duration_value(value, allow_zero=True):
    if value == 0 and allow_zero:
        return value
    if value < 5 or value % 5 != 0:
        raise serializers.ValidationError("延長時間は5分単位で入力してください")
    if value > MAX_EXTENSION_DURATION_MINUTES:
        raise serializers.ValidationError("延長時間は180分以内で入力してください")
    return value


# ──────────────────────────────────────
# Basic CRUD serializers
# ──────────────────────────────────────

class StoreSerializer(serializers.ModelSerializer):
    sip_password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Store
        fields = "__all__"


class RoomSerializer(serializers.ModelSerializer):
    area = serializers.PrimaryKeyRelatedField(
        queryset=Area.objects.all(), required=False, allow_null=True,
    )
    area_name = serializers.SerializerMethodField()

    class Meta:
        model = Room
        fields = "__all__"
        read_only_fields = ["store"]

    def validate_area(self, area):
        store = getattr(self.instance, "store", None) or self.context.get("store")
        if area is not None and (store is None or area.store_id != store.id):
            raise serializers.ValidationError("他店舗のエリアは指定できません。")
        if area is not None and not area.is_active:
            raise serializers.ValidationError("無効なエリアは指定できません。")
        return area

    @extend_schema_field(serializers.CharField())
    def get_area_name(self, obj):
        return obj.area.name if obj.area_id else ""


class AreaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Area
        fields = ["id", "store", "name", "is_active", "sort_order", "created_at", "updated_at"]
        read_only_fields = ["store", "created_at", "updated_at"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("エリア名を入力してください。")
        return value

    def validate(self, attrs):
        store = getattr(self.instance, "store", None) or self.context.get("store")
        name = attrs.get("name", getattr(self.instance, "name", ""))
        duplicate_qs = Area.objects.filter(
            store=store,
            normalized_name=normalize_area_name(name),
        )
        if self.instance:
            duplicate_qs = duplicate_qs.exclude(pk=self.instance.pk)
        if duplicate_qs.exists():
            raise serializers.ValidationError({"name": "このエリア名は既に登録されています。"})
        if attrs.get("is_active") is False and self.instance:
            used = (
                self.instance.rooms.exists()
                or self.instance.cast_preferences.exists()
                or self.instance.shift_assignments.exists()
            )
            if used:
                raise serializers.ValidationError({
                    "is_active": "部屋・希望エリア・シフトで使用中のエリアは無効化できません。先に紐づけ先を変更してください。"
                })
        return attrs


class CastExpenseTemplateInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=50)
    amount = serializers.IntegerField(min_value=0)
    memo = serializers.CharField(required=False, allow_blank=True, default="")


class CastSerializer(serializers.ModelSerializer):
    line_linked = serializers.SerializerMethodField()
    account_enabled = serializers.SerializerMethodField()
    account_username = serializers.SerializerMethodField()
    expense_templates = CastExpenseTemplateInputSerializer(
        many=True,
        required=False,
        write_only=True,
    )
    preferred_areas = serializers.SerializerMethodField()
    preferred_area_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, write_only=True,
        max_length=5,
    )

    class Meta:
        model = Cast
        fields = "__all__"
        read_only_fields = [
            "store", "line_user_id", "line_linked_at",
            "preferred_area_1", "preferred_area_2", "preferred_area_3",
            "preferred_area_4", "preferred_area_5",
        ]

    def get_line_linked(self, obj) -> bool:
        return obj.line_user_id is not None

    def get_account_enabled(self, obj) -> bool:
        return obj.user_id is not None and obj.user.is_active

    def get_account_username(self, obj) -> str:
        return obj.user.username if obj.user_id else ""

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_preferred_areas(self, obj):
        return [
            {"id": item.area_id, "name": item.area.name, "rank": item.rank}
            for item in obj.area_preferences.select_related("area").all()
        ]

    def _validate_preferred_area_ids(self, area_ids, store):
        if len(area_ids) != len(set(area_ids)):
            raise serializers.ValidationError({"preferred_area_ids": "同じエリアを複数の順位へ登録することはできません。"})
        areas = list(Area.objects.filter(id__in=area_ids, store=store, is_active=True))
        if len(areas) != len(area_ids):
            raise serializers.ValidationError({"preferred_area_ids": "同じ店舗の有効なエリアだけを指定してください。"})
        return areas

    def _replace_area_preferences(self, cast, area_ids):
        CastAreaPreference.objects.filter(cast=cast).delete()
        CastAreaPreference.objects.bulk_create([
            CastAreaPreference(cast=cast, area_id=area_id, rank=rank)
            for rank, area_id in enumerate(area_ids, start=1)
        ])

    @transaction.atomic
    def create(self, validated_data):
        expense_templates = validated_data.pop("expense_templates", [])
        area_ids = validated_data.pop("preferred_area_ids", None)
        cast = super().create(validated_data)
        request = self.context.get("request")
        edited_by = getattr(request, "user", None)

        for expense_data in expense_templates:
            template = CastExpenseTemplate.objects.create(
                store=cast.store,
                cast=cast,
                **expense_data,
            )
            CastExpenseTemplateHistory.objects.create(
                template=template,
                cast=cast,
                name=template.name,
                amount=template.amount,
                memo=template.memo,
                is_active=template.is_active,
                action=CastExpenseTemplateHistory.Action.CREATE,
                edited_by=edited_by,
            )
        if area_ids is not None:
            self._replace_area_preferences(cast, area_ids)

        return cast

    @transaction.atomic
    def update(self, instance, validated_data):
        area_ids = validated_data.pop("preferred_area_ids", None)
        cast = super().update(instance, validated_data)
        if area_ids is not None:
            self._replace_area_preferences(cast, area_ids)
        return cast

    def validate(self, attrs):
        if "option_back_rate" in attrs:
            attrs["option_fullback_enabled"] = attrs["option_back_rate"] == 100
        elif "option_fullback_enabled" in attrs:
            attrs["option_back_rate"] = 100 if attrs["option_fullback_enabled"] else 0

        if "preferred_area_ids" in self.initial_data:
            request = self.context.get("request")
            profile = get_request_profile(request)
            if profile is None or profile.role != UserProfile.Role.MANAGER:
                raise PermissionDenied("希望エリアを変更できるのはマネージャーのみです。")
        if "preferred_area_ids" in attrs:
            store = getattr(self.instance, "store", None) or self.context.get("store")
            self._validate_preferred_area_ids(attrs["preferred_area_ids"], store)

        return attrs


class CastAccountProvisionSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(min_length=8, max_length=128, write_only=True)

    def validate_username(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("ユーザー名を入力してください")
        return value

    def validate(self, attrs):
        username = attrs.get("username", "").strip()
        user = User.objects.filter(username=username).first() or User(username=username)
        try:
            validate_password_for_role(
                attrs.get("password", ""),
                user=user,
                role=UserProfile.Role.CAST,
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages}) from exc
        return attrs


class CustomerSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(source="store.name", read_only=True)
    ng_casts = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Cast.objects.all(),
        required=False,
    )

    class Meta:
        model = Customer
        fields = "__all__"
        read_only_fields = ["store", "user"]

    def validate_phone(self, value):
        phone = normalize_phone(value)
        store = self.context.get("store")
        if (
            store is not None
            and Customer.objects.filter(store=store, phone=phone)
            .exclude(pk=getattr(self.instance, "pk", None))
            .exists()
        ):
            raise serializers.ValidationError(
                "この電話番号は既に登録されています。既存顧客を選択してください。"
            )
        return phone

    def validate_ng_casts(self, casts):
        request = self.context.get("request")
        store = getattr(self.instance, "store", None) or self.context.get("store")
        if store is None and request is not None:
            store = get_user_store(request)
        if store is not None and any(cast.store_id != store.id for cast in casts):
            raise serializers.ValidationError("同じ店舗のセラピストだけを指定してください。")
        return casts

    def validate(self, attrs):
        flag = attrs.get("flag", getattr(self.instance, "flag", Customer.Flag.NONE))
        ban_type = attrs.get(
            "ban_type",
            getattr(self.instance, "ban_type", Customer.BanType.NONE),
        )
        ng_casts = attrs.get("ng_casts")
        if ng_casts and not (
            flag == Customer.Flag.BAN and ban_type == Customer.BanType.CAST_NG
        ):
            raise serializers.ValidationError({
                "ng_casts": "個別セラピストNGを選択した場合だけ対象を指定できます。",
            })
        return attrs


class CourseSerializer(serializers.ModelSerializer):
    target_cast_ids = serializers.PrimaryKeyRelatedField(
        source="target_casts", many=True,
        queryset=Cast.objects.all(), required=False,
    )

    class Meta:
        model = Course
        fields = ["id", "store", "name", "duration", "price", "target_cast_ids"]
        read_only_fields = ["store"]

    def validate(self, attrs):
        store = getattr(self.instance, "store", None) or self.context.get("store")
        target_casts = attrs.get("target_casts")
        if store is not None and target_casts is not None:
            foreign_casts = [cast for cast in target_casts if cast.store_id != store.id]
            if foreign_casts:
                raise serializers.ValidationError({
                    "target_cast_ids": "他店舗のキャストは対象にできません。",
                })
        return attrs


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

    def validate_duration(self, value):
        return validate_extension_duration_value(value, allow_zero=False)


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
    def validate_phone(self, value):
        if not re.fullmatch(r"[+0-9０-９\s()－−ー―‐-]+", value):
            raise serializers.ValidationError("電話番号のみを入力してください。")
        value = value.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
        phone = normalize_phone(value)
        # A routing identifier must be a real numeric destination.  Do not
        # accept labels or SIP addresses here: the webhook normalizes its
        # called party to this same numeric form before lookup.
        if not phone or not phone.isdigit() or not 10 <= len(phone) <= 15:
            raise serializers.ValidationError("着信先番号は10〜15桁の数字で入力してください。")
        duplicates = StorePhoneNumber.objects.filter(phone=phone)
        if self.instance:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError("この番号は既に登録されています。")
        return phone

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

    def validate(self, attrs):
        store = getattr(self.instance, "store", None) or self.context.get("store")
        cast = attrs.get("cast") or getattr(self.instance, "cast", None)
        if store is not None and cast is not None and cast.store_id != store.id:
            raise serializers.ValidationError({"cast": "他店舗のキャストは指定できません。"})
        return attrs


class CastExpenseSerializer(serializers.ModelSerializer):
    cast_name = serializers.CharField(source="cast.name", read_only=True)

    class Meta:
        model = CastExpense
        fields = "__all__"
        read_only_fields = ["store"]

    def validate(self, attrs):
        store = getattr(self.instance, "store", None) or self.context.get("store")
        cast = attrs.get("cast") or getattr(self.instance, "cast", None)
        if store is not None and cast is not None and cast.store_id != store.id:
            raise serializers.ValidationError({"cast": "他店舗のキャストは指定できません。"})
        return attrs


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
    room_name = serializers.CharField(source="room.name", read_only=True)
    compensation_amount = serializers.SerializerMethodField()
    carryover_opening_amount = serializers.SerializerMethodField()
    carryover_closing_amount = serializers.SerializerMethodField()
    cash_corrections = serializers.SerializerMethodField()
    envelope_submission = serializers.SerializerMethodField()

    class Meta:
        model = CastDailyCheckout
        fields = [
            "id", "store", "cast", "cast_name", "date", "status",
            "done_count", "total_sales", "estimated_pay", "course_sales", "options_sales", "daily_expense_total",
            "customer_payment_surcharge", "customer_payment_total",
            "payment_fee_estimate", "net_sales_after_payment_fee",
            "room", "room_name", "room_cash_taken_amount", "office_cash_paid_amount",
            "cash_returned_to_room_amount", "actual_take_home_amount",
            "compensation_amount", "carryover_opening_amount", "carryover_closing_amount",
            "checklist_json", "cast_memo", "manager_memo",
            "submitted_at", "reviewed_at", "reviewed_by", "reviewed_by_name",
            "expense_snapshots", "cash_corrections", "envelope_submission", "created_at", "updated_at",
        ]
        read_only_fields = [f for f in fields if f != "manager_memo"]

    def get_reviewed_by_name(self, obj) -> Optional[str]:
        return obj.reviewed_by.username if obj.reviewed_by else None

    @extend_schema_field({"type": "object", "nullable": True, "additionalProperties": True})
    def get_envelope_submission(self, obj):
        snapshot = obj.envelope_submissions.first()
        if not snapshot:
            return None
        return {"cash": snapshot.cash_amount, "taken": snapshot.taken_amount,
                "deposit": snapshot.deposit_amount, "withdrawal": snapshot.withdrawal_amount}

    @extend_schema_field({"type": "array", "items": {"type": "object", "additionalProperties": True}})
    def get_cash_corrections(self, obj) -> list:
        return [{
            "id": item.pk, "order": item.order_id, "reason": item.reason,
            "before": item.before, "after": item.after,
            "corrected_by_name": (item.corrected_by.get_full_name() or item.corrected_by.username) if item.corrected_by else "記録なし",
            "created_at": item.created_at.isoformat(),
        } for item in obj.cash_corrections.all()]

    def get_compensation_amount(self, obj) -> int:
        from .views import _checkout_compensation
        return _checkout_compensation(obj)

    def get_carryover_opening_amount(self, obj) -> int:
        previous = (
            CastDailyCheckout.objects.filter(cast=obj.cast, date__lt=obj.date)
            .exclude(status=CastDailyCheckout.Status.RETURNED)
            .prefetch_related("expense_snapshots")
        )
        return sum(
            self.get_compensation_amount(item)
            - item.room_cash_taken_amount - item.office_cash_paid_amount
            for item in previous
        )

    def get_carryover_closing_amount(self, obj) -> int:
        return (
            self.get_carryover_opening_amount(obj)
            + self.get_compensation_amount(obj)
            - obj.room_cash_taken_amount
            - obj.office_cash_paid_amount
        )


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
    target_cast_ids = serializers.PrimaryKeyRelatedField(
        source="target_casts",
        many=True,
        queryset=Cast.objects.all(),
        required=False,
    )
    target_cast_names = serializers.SerializerMethodField()

    class Meta:
        model = CastNote
        fields = [
            "id", "store", "title", "category", "body", "status", "status_display",
            "is_pinned", "sort_order", "visibility", "visibility_display", "video_url",
            "target_cast_ids", "target_cast_names", "image_urls",
            "created_by", "created_by_name", "updated_by", "updated_by_name",
            "published_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "store", "sort_order", "created_by", "updated_by",
            "published_at", "created_at", "updated_at",
        ]

    def get_created_by_name(self, obj) -> Optional[str]:
        return obj.created_by.username if obj.created_by else None

    def get_updated_by_name(self, obj) -> Optional[str]:
        return obj.updated_by.username if obj.updated_by else None

    def get_target_cast_names(self, obj) -> List[str]:
        return [cast.name for cast in obj.target_casts.all()]

    def validate_target_cast_ids(self, casts):
        request = self.context.get("request")
        profile = get_request_profile(request)
        if profile is None or any(cast.store_id != profile.store_id for cast in casts):
            raise serializers.ValidationError("同じ店舗のキャストだけを指定してください。")
        return casts

    def validate_image_urls(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("画像URLは一覧で指定してください。")
        if len(value) > 10:
            raise serializers.ValidationError("画像は10枚まで添付できます。")
        url_field = serializers.URLField(max_length=1000)
        return [url_field.run_validation(url) for url in value]


class CastNoteCastSerializer(serializers.ModelSerializer):
    """ノート/施術マニュアル cast本人閲覧用。読み取り専用。"""
    category_label = serializers.CharField(source="category", read_only=True)

    class Meta:
        model = CastNote
        fields = [
            "id", "title", "category", "category_label", "body",
            "is_pinned", "sort_order", "video_url", "image_urls", "published_at",
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
    # Preserve existing staff URLs: ID identifies the user's profile, scoped by store.
    id = serializers.IntegerField(source="user.profile.pk", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    avatar_url = serializers.CharField(source="user.profile.avatar_url", read_only=True)
    account_editable = serializers.SerializerMethodField()

    def get_account_editable(self, obj) -> bool:
        return not obj.user.is_superuser and not StoreMembership.objects.filter(user=obj.user).exclude(store=obj.store).exists()

    class Meta:
        model = StoreMembership
        fields = ["id", "username", "email", "role", "avatar_url", "store", "account_editable"]
        read_only_fields = ["store"]


class StaffCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=128, write_only=True)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    role = serializers.ChoiceField(
        choices=[("staff", "スタッフ"), ("manager", "マネージャー")],
        default="staff",
    )
    avatar_url = serializers.URLField(required=False, allow_blank=True, default="")

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("このユーザー名は既に使用されています")
        return value

    def validate(self, attrs):
        pending_user = User(
            username=attrs.get("username", ""),
            email=attrs.get("email", ""),
        )
        try:
            validate_password_for_role(
                attrs.get("password", ""),
                user=pending_user,
                role=attrs.get("role", UserProfile.Role.STAFF),
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages}) from exc
        return attrs

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
        return StoreMembership.objects.get(user=profile.user, store=store)


class StaffUpdateSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_blank=True)
    role = serializers.ChoiceField(
        choices=[("staff", "スタッフ"), ("manager", "マネージャー")],
        required=False,
    )
    avatar_url = serializers.URLField(required=False, allow_blank=True)
    password = serializers.CharField(max_length=128, write_only=True, required=False)

    def validate(self, attrs):
        profile = self.instance.user.profile
        global_changes = (
            bool(attrs.get("password"))
            or ("email" in attrs and attrs["email"] != self.instance.user.email)
            or ("avatar_url" in attrs and attrs["avatar_url"] != profile.avatar_url)
        )
        if global_changes and (
            self.instance.user.is_superuser
            or StoreMembership.objects.filter(user=self.instance.user).exclude(store=self.instance.store).exists()
        ):
            raise serializers.ValidationError("複数店舗を利用するアカウントの個人情報・パスワードは、本人が変更してください。")
        password = attrs.get("password")
        if password:
            try:
                validate_password_for_role(
                    password,
                    user=self.instance.user,
                    role=attrs.get("role", self.instance.role),
                )
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"password": exc.messages}) from exc
        return attrs

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        email = validated_data.pop("email", None)
        if "role" in validated_data:
            instance.role = validated_data["role"]
        instance.save()
        profile = instance.user.profile
        updates = {}
        if "avatar_url" in validated_data:
            updates["avatar_url"] = validated_data["avatar_url"]
        if profile.store_id == instance.store_id:
            updates["role"] = instance.role
        if updates:
            UserProfile.objects.filter(pk=profile.pk).update(**updates)
            for field, value in updates.items():
                setattr(profile, field, value)
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
    allow_room_overlap = serializers.BooleanField(write_only=True, required=False, default=False)
    room = serializers.PrimaryKeyRelatedField(
        queryset=Room.objects.all(),
        required=False,
        allow_null=True,
    )
    cast_name = serializers.CharField(source="cast.name", read_only=True)
    cast_avatar_url = serializers.CharField(source="cast.avatar_url", read_only=True)
    room_name = serializers.CharField(source="room.name", read_only=True)
    start_time_extended = serializers.SerializerMethodField()
    end_time_extended = serializers.SerializerMethodField()
    assigned_order_count = serializers.SerializerMethodField()
    room_auto_assigned = serializers.SerializerMethodField()
    requested_area = serializers.PrimaryKeyRelatedField(
        queryset=Area.objects.all(), required=False, allow_null=True,
    )
    requested_area_name = serializers.CharField(source="requested_area.name", read_only=True, default="")

    class Meta:
        model = ShiftAssignment
        fields = "__all__"
        read_only_fields = ["store", "clocked_in_at", "clocked_out_at"]

    def validate(self, data):
        allow_room_overlap = data.pop("allow_room_overlap", False)
        if self.instance and (self.instance.clocked_in_at or self.instance.attendance_events.exists()):
            for field in ("cast", "date"):
                if field in data and data[field] != getattr(self.instance, field):
                    raise serializers.ValidationError("打刻履歴のある勤務の日付・キャストは変更できません")
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
        start_day_offset = data.get(
            "start_day_offset",
            getattr(self.instance, "start_day_offset", 0),
        )
        end_time = data.get("end_time", getattr(self.instance, "end_time", None))
        end_day_offset = data.get(
            "end_day_offset",
            getattr(self.instance, "end_day_offset", 0),
        )

        start_at = end_at = None
        if date and start_time and end_time:
            try:
                format_extended_time(start_time, start_day_offset)
                format_extended_time(end_time, end_day_offset)
                start_at, end_at = build_business_interval(
                    date,
                    start_time,
                    end_time,
                    start_day_offset=start_day_offset,
                    end_day_offset=end_day_offset,
                    timezone_name=store.timezone if store else "Asia/Tokyo",
                )
            except BusinessDateTimeError as exc:
                raise serializers.ValidationError(str(exc)) from exc

        room_selected = "room" in data
        area_selected = "requested_area" in data and data.get("requested_area") is not None
        requested_area = data.get("requested_area", getattr(self.instance, "requested_area", None))
        room = data.get("room", getattr(self.instance, "room", None))
        if room_selected:
            # A concrete room, including an explicit "undecided" choice, is the
            # operator's decision and must not be replaced by area assignment.
            requested_area = None
            data["requested_area"] = None
        elif area_selected:
            # An area selection replaces any historical concrete-room choice.
            room = None
            data["room"] = None
        # シフトはルーム未定のまま登録できる。ルームを実在の「フリー」部屋へ
        # 置き換えると、予約・空室判定・売上集計に誤った部屋情報が混ざるため、
        # 未選択時は NULL をそのまま保持する。
        if store is not None:
            if cast is not None and cast.store_id != store.id:
                raise serializers.ValidationError("他店舗のキャストは指定できません")
            if room is not None and room.store_id != store.id:
                raise serializers.ValidationError("他店舗のルームは指定できません")
            if requested_area is not None and requested_area.store_id != store.id:
                raise serializers.ValidationError("他店舗のエリアは指定できません")
            if requested_area is not None and not requested_area.is_active:
                raise serializers.ValidationError("無効なエリアは指定できません")

        if store and cast and date and start_at and end_at:
            # Legacy requests without a room may still use area preferences.
            # An operator's explicit room choice (including null) takes priority.
            if room is None and not room_selected and (self.instance is None or area_selected):
                suggested_room = suggest_room_for_shift(
                    store,
                    cast,
                    date,
                    start_time,
                    end_time,
                    start_day_offset=start_day_offset,
                    end_day_offset=end_day_offset,
                    area=requested_area,
                )
                if suggested_room is not None:
                    data["room"] = suggested_room
                    room = suggested_room
                    self._room_auto_assigned = True
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
                        start_day_offset=existing.start_day_offset,
                        end_day_offset=existing.end_day_offset,
                        timezone_name=store.timezone,
                    )
                except BusinessDateTimeError:
                    continue
                if intervals_overlap(start_at, end_at, existing_start, existing_end):
                    raise serializers.ValidationError(
                        "このキャストの既存シフトと時間が重複しています"
                    )

            if room is not None:
                room_overlaps = []
                occupied_shifts = ShiftAssignment.objects.filter(
                    store=store,
                    room=room,
                    date__range=(date - timedelta(days=1), date + timedelta(days=1)),
                    is_absent=False,
                )
                if self.instance:
                    occupied_shifts = occupied_shifts.exclude(pk=self.instance.pk)
                for existing in occupied_shifts:
                    try:
                        existing_start, existing_end = build_business_interval(
                            existing.date,
                            existing.start_time,
                            existing.end_time,
                            start_day_offset=existing.start_day_offset,
                            end_day_offset=existing.end_day_offset,
                            timezone_name=store.timezone,
                        )
                    except BusinessDateTimeError:
                        continue
                    if intervals_overlap(start_at, end_at, existing_start, existing_end):
                        room_overlaps.append(
                            f"{room.name}：{existing.cast.name}さんのシフト"
                            f"（{existing.date} {format_extended_time(existing.start_time, existing.start_day_offset)}"
                            f"〜{format_extended_time(existing.end_time, existing.end_day_offset)}）と重なっています。"
                        )
                if room_overlaps and not allow_room_overlap:
                    raise serializers.ValidationError({"room_overlap": room_overlaps})

            room_pending_orders = Order.objects.filter(
                store=store,
                cast=cast,
                room__isnull=True,
                status__in=Order.ACTIVE_STATUSES,
                start__lt=end_at,
                end__gt=start_at,
            )
            for order in room_pending_orders:
                if order.start < start_at or order.end > end_at:
                    raise serializers.ValidationError(
                        "ルーム未定の既存予約を完全に含むシフト時間を指定してください"
                    )
                if room and Order.objects.filter(
                    room=room,
                    status__in=Order.ACTIVE_STATUSES,
                    start__lt=order.end,
                    end__gt=order.start,
                ).exists():
                    raise serializers.ValidationError(
                        "ルーム未定予約の割当先ルームが使用中です"
                    )

            self._room_pending_order_ids = list(
                room_pending_orders.values_list("id", flat=True)
            )

        return data

    def get_start_time_extended(self, obj) -> str:
        return format_extended_time(obj.start_time, obj.start_day_offset)

    def create(self, validated_data):
        with transaction.atomic():
            instance = super().create(validated_data)
            instance._room_auto_assigned = bool(
                getattr(self, "_room_auto_assigned", False)
            )
            pending_ids = getattr(self, "_room_pending_order_ids", [])
            assigned_count = 0
            if pending_ids:
                assigned_count = Order.objects.select_for_update().filter(
                    pk__in=pending_ids,
                    room__isnull=True,
                ).update(room=instance.room)
            instance._assigned_order_count = assigned_count
            return instance

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        instance._room_auto_assigned = bool(
            getattr(self, "_room_auto_assigned", False)
        )
        return instance

    def get_end_time_extended(self, obj) -> str:
        return format_extended_time(obj.end_time, obj.end_day_offset)

    def get_room_auto_assigned(self, obj) -> bool:
        return bool(getattr(obj, "_room_auto_assigned", False))

    def get_assigned_order_count(self, obj) -> int:
        return getattr(obj, "_assigned_order_count", 0)


class CastUnavailableTimeSerializer(serializers.ModelSerializer):
    cast_name = serializers.CharField(source="cast.name", read_only=True)
    type_display = serializers.CharField(source="get_type_display", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    updated_by_name = serializers.SerializerMethodField()
    business_date = serializers.DateField(write_only=True, required=False)
    start_time_extended = serializers.CharField(write_only=True, required=False)
    end_time_extended = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = CastUnavailableTime
        fields = [
            "id", "cast", "cast_name", "start_at", "end_at", "type", "type_display",
            "memo", "created_by", "created_by_name", "updated_by", "updated_by_name",
            "created_at", "updated_at", "business_date", "start_time_extended",
            "end_time_extended",
        ]
        read_only_fields = [
            "created_by", "updated_by", "created_at", "updated_at",
        ]
        extra_kwargs = {
            "start_at": {"required": False},
            "end_at": {"required": False},
        }

    def validate(self, data):
        store = (
            getattr(self.instance, "store", None)
            or self.context.get("store")
        )
        business_date = data.get("business_date")
        start_time_extended = data.get("start_time_extended")
        end_time_extended = data.get("end_time_extended")
        extended_fields = (business_date, start_time_extended, end_time_extended)
        if any(value is not None for value in extended_fields):
            if not all(value is not None for value in extended_fields):
                raise serializers.ValidationError(
                    "営業日・開始時刻・終了時刻をすべて指定してください"
                )
            try:
                start_time, start_day_offset = parse_extended_time(start_time_extended)
                end_time, end_day_offset = parse_extended_time(end_time_extended)
                data["start_at"], data["end_at"] = build_business_interval(
                    business_date,
                    start_time,
                    end_time,
                    start_day_offset=start_day_offset,
                    end_day_offset=end_day_offset,
                    timezone_name=store.timezone if store else "Asia/Tokyo",
                )
            except BusinessDateTimeError as exc:
                raise serializers.ValidationError(str(exc)) from exc

        cast = data.get("cast", getattr(self.instance, "cast", None))
        start_at = data.get("start_at", getattr(self.instance, "start_at", None))
        end_at = data.get("end_at", getattr(self.instance, "end_at", None))

        if store is None:
            raise serializers.ValidationError("所属店舗を確認できません")
        if cast is not None and cast.store_id != store.id:
            raise serializers.ValidationError({"cast": "他店舗のキャストは指定できません"})
        if self.instance is None and (start_at is None or end_at is None):
            raise serializers.ValidationError("開始日時と終了日時を指定してください")
        if start_at and end_at and end_at <= start_at:
            raise serializers.ValidationError({"end_at": "終了日時は開始日時より後にしてください"})

        if cast and start_at and end_at:
            if find_covering_shift(store, cast, start_at, end_at) is None:
                raise serializers.ValidationError(
                    "予約不可時間はキャストの出勤シフト内に設定してください"
                )
            if Order.objects.filter(
                cast=cast,
                status__in=Order.ACTIVE_STATUSES,
                start__lt=end_at,
                end__gt=start_at,
            ).exists():
                raise serializers.ValidationError(
                    "既存予約と重なるため予約不可時間を設定できません"
                )
            if cast_has_unavailable_time_conflict(
                cast,
                start_at,
                end_at,
                exclude_unavailable_time_id=getattr(self.instance, "pk", None),
            ):
                raise serializers.ValidationError("既存の予約不可時間と重複しています")

        return data

    def create(self, validated_data):
        self._remove_extended_input(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        self._remove_extended_input(validated_data)
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        business_date = business_date_for_datetime(
            instance.start_at,
            instance.store.timezone,
        )
        data["business_date"] = business_date.isoformat()
        data["start_time_extended"] = format_business_time(
            instance.start_at,
            business_date,
            instance.store.timezone,
        )
        data["end_time_extended"] = format_business_time(
            instance.end_at,
            business_date,
            instance.store.timezone,
        )
        return data

    @staticmethod
    def _remove_extended_input(validated_data):
        validated_data.pop("business_date", None)
        validated_data.pop("start_time_extended", None)
        validated_data.pop("end_time_extended", None)

    def get_created_by_name(self, obj) -> Optional[str]:
        return self._user_name(obj.created_by)

    def get_updated_by_name(self, obj) -> Optional[str]:
        return self._user_name(obj.updated_by)

    @staticmethod
    def _user_name(user) -> Optional[str]:
        if user is None:
            return None
        return user.get_full_name() or user.username


# ──────────────────────────────────────
# ShiftRequest
# ──────────────────────────────────────

class CastShiftRequestSerializer(serializers.ModelSerializer):
    cast_name = serializers.CharField(source="cast.name", read_only=True)
    desired_room_name = serializers.CharField(source="desired_room.name", read_only=True, default=None)
    approved_room_name = serializers.CharField(source="approved_room.name", read_only=True, default=None)
    decided_by_name = serializers.SerializerMethodField()
    end_time_extended = serializers.SerializerMethodField()
    start_time_extended = serializers.SerializerMethodField()
    approved_start_time_extended = serializers.SerializerMethodField()
    approved_end_time_extended = serializers.SerializerMethodField()

    class Meta:
        model = ShiftRequest
        fields = "__all__"
        # cast本人は申請内容のみ編集可。承認/却下に関するフィールドは閲覧専用にする。
        read_only_fields = [
            "store", "cast", "status", "admin_memo",
            "approved_date", "approved_start_time", "approved_start_day_offset", "approved_end_time",
            "approved_end_day_offset", "approved_room",
            "decided_at", "decided_by",
        ]

    def get_decided_by_name(self, obj) -> Optional[str]:
        if not obj.decided_by:
            return None
        return obj.decided_by.get_full_name() or obj.decided_by.username

    def validate(self, data):
        if "desired_room" in self.initial_data:
            raise serializers.ValidationError({
                "desired_room": "部屋は指定できません。希望エリアは運営が設定します。"
            })
        request = self.context.get("request")
        start_time = data.get("start_time", getattr(self.instance, "start_time", None))
        start_day_offset = data.get("start_day_offset", getattr(self.instance, "start_day_offset", 0))
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
        desired_room = data.get(
            "desired_room",
            getattr(self.instance, "desired_room", None),
        )
        if cast and desired_room and desired_room.store_id != cast.store_id:
            raise serializers.ValidationError({"desired_room": "所属店舗の部屋を選択してください"})

        date = data.get("date", getattr(self.instance, "date", None))
        start_at = end_at = None
        if cast and date and start_time and end_time:
            store = Store.objects.only("timezone", "shift_request_start_hour").get(pk=cast.store_id)
            if start_time.hour + 24 * start_day_offset < store.shift_request_start_hour:
                raise serializers.ValidationError({
                    "start_time": (
                        "開始時間は店舗設定の"
                        f"{store.shift_request_start_hour:02d}:00以降を指定してください"
                    )
                })
            try:
                format_extended_time(start_time, start_day_offset)
                format_extended_time(end_time, end_day_offset)
                start_at, end_at = build_business_interval(
                    date,
                    start_time,
                    end_time,
                    start_day_offset=start_day_offset,
                    end_day_offset=end_day_offset,
                    timezone_name=store.timezone,
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
                        start_day_offset=existing.start_day_offset,
                        end_day_offset=existing.end_day_offset,
                        timezone_name=store.timezone,
                    )
                except BusinessDateTimeError:
                    continue
                if intervals_overlap(start_at, end_at, existing_start, existing_end):
                    raise serializers.ValidationError("同じ時間帯に申請中のシフトがあります")

        return data

    def get_start_time_extended(self, obj) -> str:
        return format_extended_time(obj.start_time, obj.start_day_offset)

    def get_approved_start_time_extended(self, obj) -> Optional[str]:
        if obj.approved_start_time is None:
            return None
        return format_extended_time(obj.approved_start_time, obj.approved_start_day_offset)

    def get_end_time_extended(self, obj) -> str:
        return format_extended_time(obj.end_time, obj.end_day_offset)

    def get_approved_end_time_extended(self, obj) -> Optional[str]:
        if obj.approved_end_time is None:
            return None
        return format_extended_time(
            obj.approved_end_time,
            obj.approved_end_day_offset,
        )


class CastShiftRequestBulkItemSerializer(serializers.Serializer):
    date = serializers.DateField()
    start_time = serializers.TimeField()
    start_day_offset = serializers.IntegerField(min_value=0, max_value=1, default=0)
    end_time = serializers.TimeField()
    end_day_offset = serializers.IntegerField(min_value=0, max_value=1, default=0)
    memo = serializers.CharField(required=False, allow_blank=True)
    # 旧クライアントからの部屋指定を明示的に検知して拒否する。
    # 通常の希望シフトでは部屋を指定せず、運営がエリアと実部屋を判断する。
    desired_room = serializers.IntegerField(required=False, write_only=True)

    def validate(self, data):
        if "desired_room" in data:
            raise serializers.ValidationError({
                "desired_room": "部屋は指定できません。希望エリアは運営が設定します。"
            })
        return data


class CastShiftRequestBulkCreateSerializer(serializers.Serializer):
    dates = serializers.ListField(
        child=serializers.DateField(),
        allow_empty=False,
        max_length=31,
        required=False,
    )
    items = CastShiftRequestBulkItemSerializer(many=True, required=False, allow_empty=False)
    start_time = serializers.TimeField(required=False)
    start_day_offset = serializers.IntegerField(min_value=0, max_value=1, default=0)
    end_time = serializers.TimeField(required=False)
    end_day_offset = serializers.IntegerField(min_value=0, max_value=1, default=0)
    memo = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_dates(self, dates):
        if len(dates) != len(set(dates)):
            raise serializers.ValidationError("同じ日付が重複しています")
        return sorted(dates)

    def validate(self, data):
        if "desired_room" in self.initial_data:
            raise serializers.ValidationError({
                "desired_room": "部屋は指定できません。希望エリアは運営が設定します。"
            })
        dates = data.get("dates")
        items = data.get("items")
        if bool(dates) == bool(items):
            raise serializers.ValidationError("dates または items のどちらか一方を指定してください")

        if dates and (not data.get("start_time") or not data.get("end_time")):
            raise serializers.ValidationError(
                "dates を使用する場合は start_time と end_time を指定してください"
            )

        if items:
            item_dates = [item["date"] for item in items]
            if len(item_dates) != len(set(item_dates)):
                raise serializers.ValidationError({"items": "同じ日付が重複しています"})

        return data


class OpShiftRequestSerializer(CastShiftRequestSerializer):
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
            "approved_date", "approved_start_time", "approved_start_day_offset", "approved_end_time",
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
    reception_staff_history = serializers.SerializerMethodField()
    can_correct_accounting = serializers.SerializerMethodField()
    accounting_corrections = serializers.SerializerMethodField()
    business_date = serializers.SerializerMethodField()
    start_time_extended = serializers.SerializerMethodField()
    end_time_extended = serializers.SerializerMethodField()
    customer_label = serializers.SerializerMethodField()
    options = serializers.SerializerMethodField()
    option_ids = serializers.SerializerMethodField()
    is_unconfirmed = serializers.SerializerMethodField()
    is_past_business_day = serializers.SerializerMethodField()
    can_modify = serializers.SerializerMethodField()
    cast_name = serializers.CharField(source="cast.name", read_only=True)
    room_name = serializers.SerializerMethodField()
    is_off_shift = serializers.SerializerMethodField()
    is_room_pending = serializers.SerializerMethodField()
    service_recipient_customer_label = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    updated_by_name = serializers.SerializerMethodField()
    cancelled_by_name = serializers.SerializerMethodField()
    customer_reservation_state = serializers.SerializerMethodField()
    guest_first_opened_at = serializers.SerializerMethodField()
    guest_last_seen_state = serializers.SerializerMethodField()
    guest_open_count = serializers.SerializerMethodField()
    timeline_status_label = serializers.CharField(
        source="get_timeline_status_display",
        read_only=True,
    )
    # course_name is now a snapshot field on Order; no source override needed

    class Meta:
        model = Order
        fields = [
            "reception_staff", "reception_staff_name", "reception_staff_history",
            "id", "store", "cast", "room", "customer", "course",
            "cast_name", "room_name", "course_name", "customer_label", "service_recipient_name",
            "service_recipient_customer", "service_recipient_customer_label",
            "start", "end", "status", "timeline_status", "timeline_status_label",
            "business_date", "start_time_extended", "end_time_extended",
            "options", "option_ids", "is_unconfirmed",
            "is_past_business_day", "can_modify", "is_off_shift", "is_room_pending", "memo",
            "course_price", "options_price",
            "extension", "extension_name", "extension_duration", "extension_price",
            "nomination_fee", "nomination_fee_name", "nomination_fee_price",
            "discount", "discount_name", "discount_type_snapshot", "discount_value_snapshot", "discount_amount",
            "medium", "medium_name",
            "total_price", "payment_method", "card_include_options",
            "card_payment_confirmed_at", "card_payment_confirmed_by",
            "created_by", "created_by_name", "updated_by", "updated_by_name",
            "cancelled_by", "cancelled_by_name",
            "customer_reservation_state", "guest_first_opened_at",
            "guest_last_seen_state", "guest_open_count",
            "created_at", "updated_at",
            "can_correct_accounting", "accounting_corrections",
        ]

        read_only_fields = [
            "created_by", "updated_by", "cancelled_by",
        ]

    def get_can_correct_accounting(self, obj) -> bool:
        request = self.context.get("request")
        profile = get_request_profile(request) if request else None
        if profile is None or profile.role not in ("manager", "staff"):
            return False
        return obj.status == Order.Status.DONE and self.get_can_modify(obj) and not is_daily_settlement_locked(
            obj.store, business_date_for_datetime(obj.start, obj.store.timezone),
        )

    @extend_schema_field({"type": "array", "items": {"type": "object", "additionalProperties": True}})
    def get_accounting_corrections(self, obj) -> list:
        request = self.context.get("request")
        profile = get_request_profile(request) if request else None
        if profile is None or profile.role not in ("manager", "staff"):
            return []
        return [{
            "id": item.pk, "reason": item.reason,
            "before": item.before, "after": item.after,
            "corrected_by_name": self._operator_name(item.corrected_by),
            "created_at": item.created_at.isoformat(),
        } for item in obj.accounting_corrections.select_related("corrected_by").all()]

    @staticmethod
    def _operator_name(user) -> str:
        if not user:
            return ""
        return user.get_full_name() or user.username

    def get_created_by_name(self, obj) -> str:
        return self._operator_name(obj.created_by)

    @extend_schema_field({"type": "array", "items": {"type": "object", "additionalProperties": True}})
    def get_reception_staff_history(self, obj) -> list:
        profile = get_request_profile(self.context.get("request"))
        if profile is None or profile.role not in ("manager", "staff"):
            return []
        return [{
            "before_name": log.before.get("reception_staff_name", ""),
            "after_name": log.after.get("reception_staff_name", ""),
            "acted_by_name": self._operator_name(log.acted_by),
            "created_at": log.created_at.isoformat(),
        } for log in obj.edit_logs.all()
            if (log.before.get("reception_staff_id"), log.before.get("reception_staff_name"))
            != (log.after.get("reception_staff_id"), log.after.get("reception_staff_name"))]

    def get_updated_by_name(self, obj) -> str:
        return self._operator_name(obj.updated_by)

    def get_cancelled_by_name(self, obj) -> str:
        return self._operator_name(obj.cancelled_by)

    def get_customer_reservation_state(self, obj) -> str:
        from core.services.reservation_access import guest_reservation_state
        return guest_reservation_state(obj)

    @staticmethod
    def _guest_access(obj):
        try:
            return obj.guest_access
        except ObjectDoesNotExist:
            return None

    def get_guest_first_opened_at(self, obj) -> Optional[datetime]:
        access = self._guest_access(obj)
        return access.first_opened_at if access else None

    def get_guest_last_seen_state(self, obj) -> str:
        access = self._guest_access(obj)
        return access.last_seen_state if access else ""

    def get_guest_open_count(self, obj) -> int:
        access = self._guest_access(obj)
        return access.open_count if access else 0

    def get_customer_label(self, obj) -> str:
        return build_customer_label(obj.customer)

    def get_room_name(self, obj) -> str:
        return obj.room.name if obj.room_id else ""

    def get_is_off_shift(self, obj) -> bool:
        return find_covering_shift(obj.store, obj.cast, obj.start, obj.end) is None

    def get_is_room_pending(self, obj) -> bool:
        return obj.room_id is None

    def get_service_recipient_customer_label(self, obj) -> str:
        if not obj.service_recipient_customer_id:
            return ""
        return build_customer_label(obj.service_recipient_customer)

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

    def get_business_date(self, obj) -> str:
        return business_date_for_datetime(
            obj.start, obj.store.timezone, obj.store.business_day_boundary_hour,
        ).isoformat()

    def get_start_time_extended(self, obj) -> str:
        return self._display_order_time(obj, obj.start)

    def get_end_time_extended(self, obj) -> str:
        return self._display_order_time(obj, obj.end)

    def _display_order_time(self, obj, value):
        # Existing reservations can include seconds or extend beyond the input range.
        # Display their time without changing the stored timestamp or rejecting reads.
        local = value.astimezone(ZoneInfo(obj.store.timezone))
        business_date = date_type.fromisoformat(self.get_business_date(obj))
        hour = local.hour + (local.date() - business_date).days * 24
        return f"{hour:02d}:{local.minute:02d}"


def apply_order_extended_datetime(data, store, *, creating=False):
    """Convert the explicit reservation date and 24+ hour input using the store timezone.

    Existing clients may still submit start/end timestamps, but cannot mix the two formats.
    """
    fields = ("business_date", "start_time_extended", "end_time_extended")
    if any(field in data for field in fields):
        if "business_date" not in data or "start_time_extended" not in data:
            raise serializers.ValidationError("予約日と開始時刻を両方指定してください。")
        if "start" in data or "end" in data:
            raise serializers.ValidationError("日時と予約日・時刻を同時に指定できません。")
        business_date = data.pop("business_date")
        for field, target in (("start_time_extended", "start"), ("end_time_extended", "end")):
            if field not in data:
                continue
            value = data.pop(field)
            try:
                local_time, offset = parse_extended_time(value)
                data[target] = build_store_datetime(business_date, local_time, offset, store.timezone)
            except BusinessDateTimeError as exc:
                raise serializers.ValidationError({field: str(exc)}) from exc
    if creating and "start" not in data:
        raise serializers.ValidationError({"start": "開始日時または予約日・開始時刻を指定してください。"})


class ServiceRecipientCustomerLinkSerializer(serializers.Serializer):
    customer_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)


# ──────────────────────────────────────
# Order — create
# ──────────────────────────────────────

class ReceptionStaffMixin:
    def validate_reception_staff(self, value):
        request = self.context.get("request")
        profile = get_request_profile(request)
        if profile is None or profile.role not in ("manager", "staff"):
            raise PermissionDenied("受付スタッフを指定できるのは店舗スタッフのみです。")
        self._require_reception_member(value, profile.store)
        return value

    @staticmethod
    def _require_reception_member(user, store):
        if user is not None and not StoreMembership.objects.filter(
            user=user, store=store, is_active=True, user__is_active=True,
            role__in=("manager", "staff"),
        ).exists():
            raise serializers.ValidationError({"reception_staff": "この店舗の有効なスタッフを選択してください。"})

    def _set_reception_name(self, data, store):
        if "reception_staff" in data:
            user = data["reception_staff"]
            self._require_reception_member(user, store)
            data["reception_staff_name"] = (user.get_full_name() or user.username) if user else ""


class OrderCreateSerializer(ReceptionStaffMixin, serializers.ModelSerializer):
    business_date = serializers.DateField(write_only=True, required=False)
    start_time_extended = serializers.CharField(write_only=True, required=False)
    end_time_extended = serializers.CharField(write_only=True, required=False)
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
    nomination_fee = serializers.PrimaryKeyRelatedField(
        queryset=NominationFee.objects.all(), required=False, allow_null=True,
    )
    extension_duration = serializers.IntegerField(
        required=False,
        min_value=0,
        max_value=MAX_EXTENSION_DURATION_MINUTES,
    )
    extension_price = serializers.IntegerField(required=False, min_value=0)

    class Meta:
        model = Order
        fields = [
            "reception_staff",
            "cast", "customer", "course", "start", "end",
            "service_recipient_name", "memo", "options", "extension", "extension_duration", "extension_price",
            "nomination_fee", "medium", "discount", "payment_method", "card_include_options",
            "business_date", "start_time_extended", "end_time_extended",
        ]
        extra_kwargs = {
            "start": {"required": False},
            "end": {"required": False},
            "memo": {"required": False, "default": ""},
            "payment_method": {"required": False},
        }

    def validate(self, data):
        store = data["customer"].store
        expected_store = self.context.get("store")
        if expected_store is not None and store.id != expected_store.id:
            raise serializers.ValidationError({"customer": "他店舗の顧客は使用できません"})
        call = getattr(self.context.get("request"), "_roomink_call", None)
        if call and call.from_phone.isascii() and call.from_phone.isdigit():
            if data["customer"].phone != call.from_phone:
                raise serializers.ValidationError({"customer": "着信元の顧客を選択してください。"})
        data["store"] = store
        apply_order_extended_datetime(data, store, creating=True)

        settlement_date = business_date_for_datetime(data["start"], store.timezone)
        if is_daily_settlement_locked(store, settlement_date):
            raise serializers.ValidationError(
                "この営業日は日締め済みです。変更するには先に日締めを解除してください。"
            )

        for field_name in ("cast", "course", "medium"):
            value = data.get(field_name)
            if value is not None and value.store_id != store.id:
                raise serializers.ValidationError({
                    field_name: "他店舗のデータは使用できません",
                })
        foreign_options = [option for option in data.get("options", []) if option.store_id != store.id]
        if foreign_options:
            raise serializers.ValidationError({"options": "他店舗のオプションは使用できません"})

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
        from .services.booking_restrictions import customer_booking_blocked
        profile = get_request_profile(request) if request else None
        operator = profile is not None and profile.role in (UserProfile.Role.MANAGER, UserProfile.Role.STAFF)
        if customer_booking_blocked(customer, data["cast"].pk, online=not operator):
            raise serializers.ValidationError("このお客様は予約を受け付けられません")

        extension = data.get("extension")
        if extension is not None:
            if extension.store_id != store.id:
                raise serializers.ValidationError({"extension": "他店舗の延長は使用できません"})
            if not extension.is_active:
                raise serializers.ValidationError({"extension": "無効な延長は使用できません"})

        extension_duration = data.get(
            "extension_duration",
            extension.duration if extension is not None else 0,
        )
        extension_price = data.get(
            "extension_price",
            extension.price if extension is not None else 0,
        )
        validate_extension_duration_value(extension_duration)
        request = self.context.get("request")
        profile = get_request_profile(request) if request else None
        if extension_duration and (
            profile is None
            or profile.role not in (UserProfile.Role.MANAGER, UserProfile.Role.STAFF)
        ):
            raise PermissionDenied("延長を設定できるのはマネージャーまたはスタッフのみです。")
        if extension is not None and extension_duration == 0:
            raise serializers.ValidationError({"extension_duration": "延長時間は1分以上にしてください"})
        if extension_duration == 0 and extension_price:
            raise serializers.ValidationError({"extension_price": "延長時間が0分の場合、料金は0円にしてください"})
        data["extension_duration"] = extension_duration
        data["extension_price"] = extension_price

        nomination_fee = data.get("nomination_fee")
        if nomination_fee is not None:
            if nomination_fee.store_id != store.id:
                raise serializers.ValidationError({"nomination_fee": "他店舗の指名料は使用できません"})
            if not nomination_fee.is_active:
                raise serializers.ValidationError({"nomination_fee": "無効な指名料は使用できません"})

        if data.get("payment_method", Order.PaymentMethod.UNSET) != Order.PaymentMethod.CARD:
            data["card_include_options"] = False

        # B) end auto-calc（延長選択時は終了時刻へ必ず反映）
        course = data["course"]
        if extension_duration:
            data["end"] = data["start"] + timedelta(
                minutes=course.duration + extension_duration,
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
            profile = get_request_profile(request) if request else None
            if profile is None or profile.role not in (
                UserProfile.Role.MANAGER,
                UserProfile.Role.STAFF,
            ):
                raise PermissionDenied(
                    "シフト外予約を作成できるのはマネージャーまたはスタッフのみです。"
                )
            data["room"] = None
        else:
            data["room"] = assignment.room

        if cast_has_unavailable_time_conflict(data["cast"], start, end):
            raise serializers.ValidationError("指定時間はこのキャストの予約不可時間です")

        # D) cast conflict (既存予約の end + interval_minutes をインターバル占有終端とみなす)
        cast_obj = data["cast"]
        if cast_has_order_conflict(cast_obj, start, end):
            raise serializers.ValidationError(
                "このキャストは指定時間に予約が入っています（インターバル含む）"
            )

        # E) room conflict
        if data["room"] is not None and Order.objects.filter(
            room=data["room"], status__in=Order.ACTIVE_STATUSES,
            start__lt=end, end__gt=start,
        ).exists():
            raise serializers.ValidationError("指定ルームは使用中です")

        # F) discount cross-store check
        discount = data.get("discount")
        if discount is not None and discount.store_id != store.id:
            raise serializers.ValidationError("他店舗の割引は使用できません")
        if discount is not None and not discount.is_active:
            raise serializers.ValidationError("無効な割引は使用できません")

        return data

    def validate_service_recipient_name(self, value):
        request = self.context.get("request")
        if request:
            profile = get_request_profile(request)
            if profile is None or profile.role not in (
                UserProfile.Role.MANAGER,
                UserProfile.Role.STAFF,
            ):
                raise PermissionDenied(
                    "実利用者名を設定できるのはマネージャーまたはスタッフのみです。"
                )
        return value.strip()

    def create(self, validated_data):
        from .services.pricing import recalculate_order_total
        with transaction.atomic():
            # 日締め確定と同じ店舗行をロックし、検証後のすり抜けを防ぐ。
            store = Store.objects.select_for_update().get(pk=validated_data["store"].pk)
            if is_daily_settlement_locked(
                store,
                business_date_for_datetime(validated_data["start"], store.timezone),
            ):
                raise serializers.ValidationError(
                    "この営業日は日締め済みです。変更するには先に日締めを解除してください。"
                )
            # 画面での空き判定から保存までの競合を直列化し、ロック取得後に再検査する。
            cast = Cast.objects.select_for_update().get(
                pk=validated_data["cast"].pk,
                store=store,
            )
            validated_data["cast"] = cast
            room = validated_data.get("room")
            if room is not None:
                room = Room.objects.select_for_update().get(pk=room.pk, store=store)
                validated_data["room"] = room
            start = validated_data["start"]
            end = validated_data["end"]
            if cast_has_order_conflict(cast, start, end):
                raise serializers.ValidationError(
                    "このキャストは指定時間に予約が入っています（インターバル含む）"
                )
            if room is not None and Order.objects.filter(
                room=room,
                status__in=Order.ACTIVE_STATUSES,
                start__lt=end,
                end__gt=start,
            ).exists():
                raise serializers.ValidationError("指定ルームは使用中です")
            option_objs = validated_data.pop("options", [])
            if "reception_staff" not in validated_data:
                request = self.context.get("request")
                profile = get_request_profile(request)
                if profile and profile.role in ("manager", "staff") and StoreMembership.objects.filter(
                    user=request.user, store=store, is_active=True, user__is_active=True,
                    role__in=("manager", "staff"),
                ).exists():
                    validated_data["reception_staff"] = request.user
            self._set_reception_name(validated_data, store)
            course = validated_data["course"]
            validated_data["course_name"] = course.name
            validated_data["course_price"] = course.price
            opts_total = sum(o.price for o in option_objs)
            validated_data["options_price"] = opts_total
            extension = validated_data.get("extension")
            extension_duration = validated_data.get("extension_duration", 0)
            if extension_duration:
                validated_data["extension_name"] = (
                    extension.name
                    if extension and extension_duration == extension.duration
                    else f"{extension_duration}分延長"
                )
            nomination_fee = validated_data.get("nomination_fee")
            if nomination_fee:
                validated_data["nomination_fee_name"] = nomination_fee.name
                validated_data["nomination_fee_price"] = nomination_fee.price
            else:
                request = self.context.get("request")
                profile = get_request_profile(request) if request else None
                if profile and profile.role in (
                    UserProfile.Role.MANAGER,
                    UserProfile.Role.STAFF,
                ):
                    # 店舗手入力の「指名なし」は顧客向けには「フリー」と表示する。
                    # 公開Web予約は request を渡さないため、選択したキャスト名を維持する。
                    validated_data["nomination_fee_name"] = "フリー"
                    validated_data["nomination_fee_price"] = 0
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


class ExtensionApplySerializer(serializers.Serializer):
    extension_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    extension_duration = serializers.IntegerField(
        required=False,
        min_value=0,
        max_value=MAX_EXTENSION_DURATION_MINUTES,
    )
    extension_price = serializers.IntegerField(required=False, min_value=0)

    def validate_extension_duration(self, value):
        return validate_extension_duration_value(value)


# ──────────────────────────────────────
# Order — update (partial)
# ──────────────────────────────────────

class OrderUpdateSerializer(ReceptionStaffMixin, serializers.ModelSerializer):
    expected_updated_at = serializers.DateTimeField(write_only=True, required=False)
    business_date = serializers.DateField(write_only=True, required=False)
    start_time_extended = serializers.CharField(write_only=True, required=False)
    end_time_extended = serializers.CharField(write_only=True, required=False)
    options = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Option.objects.all(), required=False,
    )
    nomination_fee = serializers.PrimaryKeyRelatedField(
        queryset=NominationFee.objects.all(), required=False, allow_null=True,
    )
    discount = serializers.PrimaryKeyRelatedField(queryset=Discount.objects.all(), required=False, allow_null=True)
    extension = serializers.PrimaryKeyRelatedField(queryset=Extension.objects.all(), required=False, allow_null=True)
    extension_duration = serializers.IntegerField(required=False, min_value=0, max_value=MAX_EXTENSION_DURATION_MINUTES)
    extension_price = serializers.IntegerField(required=False, min_value=0)

    class Meta:
        model = Order
        fields = [
            "reception_staff",
            "cast", "course", "start", "end", "service_recipient_name",
            "memo", "medium", "options", "nomination_fee", "payment_method", "card_include_options",
            "timeline_status", "expected_updated_at", "discount", "extension", "extension_duration", "extension_price",
            "business_date", "start_time_extended", "end_time_extended",
        ]

    def validate_service_recipient_name(self, value):
        request = self.context.get("request")
        profile = get_request_profile(request) if request else None
        if profile is None or profile.role not in (
            UserProfile.Role.MANAGER,
            UserProfile.Role.STAFF,
        ):
            raise PermissionDenied(
                "実利用者名を変更できるのはマネージャーまたはスタッフのみです。"
            )
        return value.strip()

    def validate(self, data):
        instance = self.instance
        if instance.status == Order.Status.CANCELLED or (
            instance.status == Order.Status.DONE and not self.context.get("allow_completed_addons")
        ):
            raise serializers.ValidationError("会計完了またはキャンセル済みの予約は変更できません。")
        apply_order_extended_datetime(data, instance.store)
        cast = data.get("cast", instance.cast)
        start = data.get("start", instance.start)
        end = data.get("end", instance.end)

        for field in ("discount", "extension"):
            value = data.get(field)
            if value is not None and (value.store_id != instance.store_id or not value.is_active):
                raise serializers.ValidationError({field: "この店舗の有効な項目を選択してください"})
        extension = data.get("extension", instance.extension)
        if "extension" in data:
            data.setdefault("extension_duration", extension.duration if extension else 0)
            data.setdefault("extension_price", extension.price if extension else 0)
        duration = data.get("extension_duration", instance.extension_duration)
        price = data.get("extension_price", instance.extension_price)
        validate_extension_duration_value(duration)
        if extension is not None and duration == 0:
            raise serializers.ValidationError({"extension_duration": "延長時間は1分以上にしてください"})
        if duration == 0 and price:
            raise serializers.ValidationError({"extension_price": "延長時間が0分の場合、料金は0円にしてください"})
        course = data.get("course", instance.course)
        if course.pk != instance.course_id or duration != instance.extension_duration:
            end = start + timedelta(minutes=course.duration + duration)
            data["end"] = end

        for business_date in {
            business_date_for_datetime(instance.start, instance.store.timezone),
            business_date_for_datetime(start, instance.store.timezone),
        }:
            if is_daily_settlement_locked(instance.store, business_date):
                raise serializers.ValidationError(
                    "この営業日は日締め済みです。変更するには先に日締めを解除してください。"
                )

        for field_name in ("cast", "course", "medium"):
            value = data.get(field_name)
            if value is not None and value.store_id != instance.store_id:
                raise serializers.ValidationError({
                    field_name: "他店舗のデータは使用できません",
                })
        foreign_options = [option for option in data.get("options", []) if option.store_id != instance.store_id]
        if foreign_options:
            raise serializers.ValidationError({"options": "他店舗のオプションは使用できません"})

        nomination_fee = data.get("nomination_fee", instance.nomination_fee)
        if nomination_fee is not None:
            if nomination_fee.store_id != instance.store_id:
                raise serializers.ValidationError({"nomination_fee": "他店舗の指名料は使用できません"})
            if not nomination_fee.is_active:
                raise serializers.ValidationError({"nomination_fee": "無効な指名料は使用できません"})

        payment_method = data.get("payment_method", instance.payment_method)
        if payment_method != Order.PaymentMethod.CARD:
            data["card_include_options"] = False

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
            end = start + timedelta(minutes=data["course"].duration + duration)
            data["end"] = end

        if end <= start:
            raise serializers.ValidationError("終了時刻は開始時刻より後にしてください")

        time_or_cast_changed = "cast" in data or "start" in data or "end" in data
        if time_or_cast_changed:
            store = instance.store

            # ShiftAssignment → room auto-assign
            assignment = find_covering_shift(store, cast, start, end)
            if assignment is None:
                if (instance.room_id is not None and cast.pk == instance.cast_id
                        and start == instance.start
                        and (course.pk != instance.course_id or duration != instance.extension_duration)):
                    raise serializers.ValidationError("変更後の終了時刻がキャストのシフトを超えます")
                profile = get_request_profile(request) if request else None
                if profile is None or profile.role not in (
                    UserProfile.Role.MANAGER,
                    UserProfile.Role.STAFF,
                ):
                    raise PermissionDenied(
                        "シフト外予約へ変更できるのはマネージャーまたはスタッフのみです。"
                    )
                data["room"] = None
            else:
                data["room"] = assignment.room

            if cast_has_unavailable_time_conflict(cast, start, end):
                raise serializers.ValidationError("指定時間はこのキャストの予約不可時間です")

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
            if data["room"] is not None and Order.objects.filter(
                room=data["room"], status__in=Order.ACTIVE_STATUSES,
                start__lt=end, end__gt=start,
            ).exclude(pk=instance.pk).exists():
                raise serializers.ValidationError("指定ルームは使用中です")

        return data

    def update(self, instance, validated_data):
        with transaction.atomic():
            store = Store.objects.select_for_update().get(pk=instance.store_id)
            # Never save the stale object loaded before waiting for this lock.
            instance = Order.objects.select_for_update().get(pk=instance.pk, store=store)
            require_current_order(
                instance, validated_data.pop("expected_updated_at", None),
                required="options" in validated_data or "reception_staff" in validated_data,
            )
            if instance.status == Order.Status.CANCELLED or (
                instance.status == Order.Status.DONE and not self.context.get("allow_completed_addons")
            ):
                raise serializers.ValidationError("会計完了またはキャンセル済みの予約は変更できません。")
            target_start = validated_data.get("start", instance.start)
            for business_date in {
                business_date_for_datetime(instance.start, store.timezone),
                business_date_for_datetime(target_start, store.timezone),
            }:
                if is_daily_settlement_locked(store, business_date):
                    raise serializers.ValidationError(
                        "この営業日は日締め済みです。変更するには先に日締めを解除してください。"
                    )
            target_cast = Cast.objects.select_for_update().get(
                pk=validated_data.get("cast", instance.cast).pk,
                store=store,
            )
            target_start = validated_data.get("start", instance.start)
            target_end = validated_data.get("end", instance.end)
            target_room = validated_data.get("room", instance.room)
            if target_room is not None:
                target_room = Room.objects.select_for_update().get(
                    pk=target_room.pk,
                    store=store,
                )
                validated_data["room"] = target_room
            if ("cast" in validated_data or "start" in validated_data or "end" in validated_data):
                if cast_has_order_conflict(
                    target_cast,
                    target_start,
                    target_end,
                    exclude_order_id=instance.pk,
                ):
                    raise serializers.ValidationError(
                        "このキャストは指定時間に予約が入っています（インターバル含む）"
                    )
                if target_room is not None and Order.objects.filter(
                    room=target_room,
                    status__in=Order.ACTIVE_STATUSES,
                    start__lt=target_end,
                    end__gt=target_start,
                ).exclude(pk=instance.pk).exists():
                    raise serializers.ValidationError("指定ルームは使用中です")
            before = order_edit_snapshot(instance)
            self._set_reception_name(validated_data, store)
            instance = self._update_unlocked(instance, validated_data)
            request = self.context.get("request")
            record_order_edit(instance, before, request.user if request else None, "operator")
            return instance

    def _update_unlocked(self, instance, validated_data):
        option_objs = validated_data.pop("options", None)

        if "discount" in validated_data:
            discount = validated_data["discount"]
            validated_data["discount_name"] = discount.name if discount else ""
            validated_data["discount_type_snapshot"] = discount.discount_type if discount else ""
            validated_data["discount_value_snapshot"] = discount.value if discount else 0
        if any(field in validated_data for field in ("extension", "extension_duration", "extension_price")):
            extension = validated_data.get("extension", instance.extension)
            duration = validated_data.get("extension_duration", instance.extension_duration)
            validated_data["extension_name"] = (
                extension.name if extension and extension.duration == duration else f"{duration}分延長"
            ) if duration else ""

        if "nomination_fee" in validated_data:
            nomination_fee = validated_data["nomination_fee"]
            validated_data["nomination_fee_name"] = nomination_fee.name if nomination_fee else "フリー"
            validated_data["nomination_fee_price"] = nomination_fee.price if nomination_fee else 0

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
    updated_at = serializers.DateTimeField()
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    start_time_extended = serializers.CharField()
    end_time_extended = serializers.CharField()
    status = serializers.CharField()
    customer_reservation_state = serializers.CharField()
    room_id = serializers.IntegerField(allow_null=True)
    room_name = serializers.CharField(allow_blank=True)
    is_room_pending = serializers.BooleanField()
    customer_label = serializers.CharField()
    reservation_name = serializers.CharField()
    service_recipient_name = serializers.CharField(allow_blank=True)
    course_name = serializers.CharField()
    course_price = serializers.IntegerField()
    option_ids = serializers.ListField(child=serializers.IntegerField())
    options = serializers.ListField(child=serializers.DictField())
    options_price = serializers.IntegerField()
    nomination_fee_name = serializers.CharField(allow_blank=True)
    nomination_fee_price = serializers.IntegerField()
    total_price = serializers.IntegerField()
    payment_method = serializers.CharField()
    payment_method_label = serializers.CharField()
    memo = serializers.CharField()
    is_unconfirmed = serializers.BooleanField()


# ──────────────────────────────────────
# Schedule API serializers
# ──────────────────────────────────────

class ScheduleShiftSerializer(serializers.ModelSerializer):
    room_name = serializers.CharField(source="room.name", read_only=True)
    room_color = serializers.CharField(source="room.background_color", read_only=True, default="")
    start_time_extended = serializers.SerializerMethodField()
    end_time_extended = serializers.SerializerMethodField()

    class Meta:
        model = ShiftAssignment
        fields = [
            "id", "room_id", "room_name", "room_color",
            "start_time", "start_day_offset", "start_time_extended",
            "end_time", "end_day_offset", "end_time_extended",
            "clocked_in_at", "confirmed_at",
            "daily_memo", "is_absent",
        ]

    def get_start_time_extended(self, obj) -> str:
        return format_extended_time(obj.start_time, obj.start_day_offset)

    def get_end_time_extended(self, obj) -> str:
        return format_extended_time(obj.end_time, obj.end_day_offset)


class ScheduleCastSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    avatar_url = serializers.CharField()
    interval_minutes = serializers.IntegerField()
    staff_memo = serializers.CharField(allow_blank=True, required=False)
    is_off_shift = serializers.BooleanField()
    shifts = ScheduleShiftSerializer(many=True)


class ScheduleOrderSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    cast_id = serializers.IntegerField()
    room_id = serializers.IntegerField(allow_null=True)
    customer_label = serializers.CharField()
    service_recipient_name = serializers.CharField(allow_blank=True)
    course_name = serializers.CharField()
    nomination_fee_name = serializers.CharField(allow_blank=True)
    extension_duration = serializers.IntegerField()
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    start_time_extended = serializers.CharField()
    end_time_extended = serializers.CharField()
    status = serializers.CharField()
    timeline_status = serializers.CharField()
    timeline_status_label = serializers.CharField()
    customer_reservation_state = serializers.CharField()
    options = serializers.ListField(child=serializers.CharField())
    is_unconfirmed = serializers.BooleanField()
    is_off_shift = serializers.BooleanField()
    is_room_pending = serializers.BooleanField()


class ScheduleUnavailableTimeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    cast_id = serializers.IntegerField()
    cast_name = serializers.CharField()
    start_at = serializers.DateTimeField()
    end_at = serializers.DateTimeField()
    start_time_extended = serializers.CharField()
    end_time_extended = serializers.CharField()
    type = serializers.CharField()
    type_display = serializers.CharField()
    memo = serializers.CharField(allow_blank=True)


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
    unavailable_times = ScheduleUnavailableTimeSerializer(many=True)
    kpi = ScheduleKpiSerializer()


def build_schedule_data(store, date):
    from core.services.reservation_access import guest_reservation_state

    shifts = (
        ShiftAssignment.objects
        .filter(store=store, date=date)
        .select_related("room", "cast")
        .order_by("start_day_offset", "start_time", "id")
    )

    shifts_by_cast = defaultdict(list)
    for s in shifts:
        shifts_by_cast[s.cast_id].append(s)

    casts = Cast.objects.filter(store=store).order_by("name")

    # タイムライン表示順: display_order（1〜）が設定されたキャストを先頭に、
    # 未設定（0）は従来どおり名前順で後ろに並べる。
    def _cast_sort_key(c):
        active_shifts = [s for s in shifts_by_cast.get(c.id, []) if not s.is_absent]
        if not active_shifts:
            return (2, 0, c.name)
        orders_set = [
            s.display_order for s in active_shifts if s.display_order
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
            "is_off_shift": not any(
                not shift.is_absent for shift in shifts_by_cast.get(c.id, [])
            ),
            "shifts": shifts_by_cast.get(c.id, []),
        })

    range_start, range_end = business_day_range(
        date, store.timezone, store.business_day_boundary_hour,
    )
    orders = (
        Order.objects
        .filter(store=store, start__gte=range_start, start__lt=range_end)
        .exclude(status=Order.Status.CANCELLED)
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
            "service_recipient_name": o.service_recipient_name,
            "course_name": o.course_name,
            "nomination_fee_name": o.nomination_fee_name,
            "extension_duration": o.extension_duration,
            "start": o.start,
            "end": o.end,
            "start_time_extended": format_business_time(o.start, date, store.timezone),
            "end_time_extended": format_business_time(o.end, date, store.timezone),
            "status": o.status,
            "timeline_status": o.timeline_status,
            "timeline_status_label": o.get_timeline_status_display(),
            "customer_reservation_state": guest_reservation_state(o),
            "options": [opt.name for opt in o.options.all()],
            "is_unconfirmed": o.id not in acked_order_ids,
            "is_off_shift": find_covering_shift(store, o.cast, o.start, o.end) is None,
            "is_room_pending": o.room_id is None,
        })

    unavailable_times = CastUnavailableTime.objects.filter(
        store=store,
        start_at__lt=range_end,
        end_at__gt=range_start,
    ).select_related("cast")
    unavailable_time_data = [
        {
            "id": unavailable.id,
            "cast_id": unavailable.cast_id,
            "cast_name": unavailable.cast.name,
            "start_at": unavailable.start_at,
            "end_at": unavailable.end_at,
            "start_time_extended": format_business_time(
                unavailable.start_at, date, store.timezone,
            ),
            "end_time_extended": format_business_time(
                unavailable.end_at, date, store.timezone,
            ),
            "type": unavailable.type,
            "type_display": unavailable.get_type_display(),
            "memo": unavailable.memo,
        }
        for unavailable in unavailable_times
    ]

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
        "unavailable_times": unavailable_time_data,
        "kpi": kpi,
    }


def build_room_schedule_data(store, date):
    from core.services.reservation_access import guest_reservation_state

    rooms = Room.objects.filter(store=store).order_by("sort_order")

    range_start, range_end = business_day_range(
        date, store.timezone, store.business_day_boundary_hour,
    )
    orders = (
        Order.objects
        .filter(
            store=store,
            start__gte=range_start,
            start__lt=range_end,
            room__isnull=False,
        )
        .exclude(status=Order.Status.CANCELLED)
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
            "service_recipient_name": o.service_recipient_name,
            "course_name": o.course_name,
            "start": o.start,
            "end": o.end,
            "start_time_extended": format_business_time(o.start, date, store.timezone),
            "end_time_extended": format_business_time(o.end, date, store.timezone),
            "status": o.status,
            "timeline_status": o.timeline_status,
            "timeline_status_label": o.get_timeline_status_display(),
            "customer_reservation_state": guest_reservation_state(o),
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
            "is_repeat", "duration_seconds", "created_at", "updated_at",
            "notes",
        ]
        read_only_fields = [
            "id", "contact_id", "status", "assigned_to", "is_repeat", "duration_seconds",
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
            "provider", "provider_message_id", "provider_status",
            "encoding", "segment_count", "delivered_at", "error_message",
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
