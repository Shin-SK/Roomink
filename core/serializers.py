from datetime import timedelta
from collections import defaultdict

from rest_framework import serializers

from .utils.phone import normalize_phone
from django.contrib.auth import get_user_model

from .models import (
    Cast,
    CastAck,
    Course,
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
    ShiftRequest,
    Store,
    UserProfile,
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
    class Meta:
        model = Cast
        fields = "__all__"
        read_only_fields = ["store"]


class CustomerSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(source="store.name", read_only=True)

    class Meta:
        model = Customer
        fields = "__all__"
        read_only_fields = ["store"]

    def validate_phone(self, value):
        return normalize_phone(value)


class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = "__all__"
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
        store = validated_data.pop("store")
        role = validated_data.pop("role", "staff")
        avatar_url = validated_data.pop("avatar_url", "")
        user = User.objects.create_user(
            username=validated_data["username"],
            password=validated_data["password"],
            email=validated_data.get("email", ""),
        )
        profile = UserProfile.objects.create(
            user=user, store=store, role=role, avatar_url=avatar_url,
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
    room_name = serializers.CharField(source="room.name", read_only=True)

    class Meta:
        model = ShiftAssignment
        fields = "__all__"
        read_only_fields = ["store"]

    def validate(self, data):
        store = data.get("store", getattr(self.instance, "store", None))
        date = data.get("date", getattr(self.instance, "date", None))
        cast = data.get("cast", getattr(self.instance, "cast", None))
        start_time = data.get("start_time", getattr(self.instance, "start_time", None))
        end_time = data.get("end_time", getattr(self.instance, "end_time", None))

        if start_time and end_time and end_time <= start_time:
            raise serializers.ValidationError("end_time は start_time より後にしてください")

        qs = ShiftAssignment.objects.filter(
            store=store, date=date, cast=cast,
            start_time__lt=end_time,
            end_time__gt=start_time,
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("このキャストの既存シフトと時間が重複しています")

        return data


# ──────────────────────────────────────
# ShiftRequest
# ──────────────────────────────────────

class CastShiftRequestSerializer(serializers.ModelSerializer):
    cast_name = serializers.CharField(source="cast.name", read_only=True)
    desired_room_name = serializers.CharField(source="desired_room.name", read_only=True, default=None)

    class Meta:
        model = ShiftRequest
        fields = "__all__"
        read_only_fields = ["store", "cast", "status", "admin_memo"]

    def validate(self, data):
        start_time = data.get("start_time", getattr(self.instance, "start_time", None))
        end_time = data.get("end_time", getattr(self.instance, "end_time", None))

        if start_time and end_time and end_time <= start_time:
            raise serializers.ValidationError("end_time は start_time より後にしてください")

        # 同一キャスト・同一時間帯の REQUESTED 重複チェック
        cast = data.get("cast", getattr(self.instance, "cast", None))
        date = data.get("date", getattr(self.instance, "date", None))
        if cast and date and start_time and end_time:
            qs = ShiftRequest.objects.filter(
                cast=cast, date=date,
                status=ShiftRequest.Status.REQUESTED,
                start_time__lt=end_time,
                end_time__gt=start_time,
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError("同じ時間帯に申請中のシフトがあります")

        return data


class OpShiftRequestSerializer(serializers.ModelSerializer):
    cast_name = serializers.CharField(source="cast.name", read_only=True)
    desired_room_name = serializers.CharField(source="desired_room.name", read_only=True, default=None)

    class Meta:
        model = ShiftRequest
        fields = "__all__"
        read_only_fields = ["store", "cast"]


# ──────────────────────────────────────
# Order — read
# ──────────────────────────────────────

def build_customer_label(customer):
    name = customer.display_name or customer.phone
    if customer.flag == Customer.Flag.BAN:
        return f"{name} ★BAN"
    if customer.flag == Customer.Flag.ATTENTION:
        return f"{name} ★注意"
    return name


class OrderSerializer(serializers.ModelSerializer):
    customer_label = serializers.SerializerMethodField()
    options = serializers.SerializerMethodField()
    option_ids = serializers.SerializerMethodField()
    is_unconfirmed = serializers.SerializerMethodField()
    cast_name = serializers.CharField(source="cast.name", read_only=True)
    room_name = serializers.CharField(source="room.name", read_only=True)
    # course_name is now a snapshot field on Order; no source override needed

    class Meta:
        model = Order
        fields = [
            "id", "store", "cast", "room", "customer", "course",
            "cast_name", "room_name", "course_name", "customer_label",
            "start", "end", "status", "options", "option_ids", "is_unconfirmed", "memo",
            "course_price", "options_price",
            "extension", "extension_name", "extension_price",
            "nomination_fee", "nomination_fee_name", "nomination_fee_price",
            "discount", "discount_name", "discount_type_snapshot", "discount_value_snapshot", "discount_amount",
            "medium", "medium_name",
            "total_price",
            "created_at", "updated_at",
        ]

    def get_customer_label(self, obj):
        return build_customer_label(obj.customer)

    def get_options(self, obj):
        # prefetch_related 済みの場合 DB クエリを避ける
        if hasattr(obj, '_prefetched_objects_cache') and 'options' in obj._prefetched_objects_cache:
            return [o.name for o in obj.options.all()]
        return list(obj.options.values_list("name", flat=True))

    def get_option_ids(self, obj):
        return list(obj.options.values_list("id", flat=True))

    def get_is_unconfirmed(self, obj):
        return not CastAck.objects.filter(order=obj, acked_at__isnull=False).exists()


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

    class Meta:
        model = Order
        fields = [
            "cast", "customer", "course", "start", "end",
            "memo", "options", "medium",
        ]
        extra_kwargs = {
            "end": {"required": False},
            "memo": {"required": False, "default": ""},
        }

    def validate(self, data):
        store = data["customer"].store
        data["store"] = store

        # A) BAN check
        customer = data["customer"]
        if customer.flag == Customer.Flag.BAN:
            raise serializers.ValidationError("このお客様は予約を受け付けられません")

        # B) end auto-calc
        course = data["course"]
        if not data.get("end"):
            data["end"] = data["start"] + timedelta(minutes=course.duration)
        if data["end"] <= data["start"]:
            raise serializers.ValidationError("終了時刻は開始時刻より後にしてください")

        # C) ShiftAssignment → room
        start = data["start"]
        end = data["end"]
        assignment = ShiftAssignment.objects.filter(
            store=store,
            date=start.date(),
            cast=data["cast"],
            start_time__lte=start.time(),
            end_time__gte=end.time(),
        ).first()
        if assignment is None:
            raise serializers.ValidationError("このキャストは指定日時にシフトがありません")
        data["room"] = assignment.room

        # D) cast conflict
        if Order.objects.filter(
            cast=data["cast"],
            status__in=Order.ACTIVE_STATUSES,
            start__lt=end,
            end__gt=start,
        ).exists():
            raise serializers.ValidationError("このキャストは指定時間に予約が入っています")

        # E) room conflict
        if Order.objects.filter(
            room=data["room"],
            status__in=Order.ACTIVE_STATUSES,
            start__lt=end,
            end__gt=start,
        ).exists():
            raise serializers.ValidationError("指定ルームは使用中です")

        return data

    def create(self, validated_data):
        option_objs = validated_data.pop("options", [])
        course = validated_data["course"]
        validated_data["course_name"] = course.name
        validated_data["course_price"] = course.price
        opts_total = sum(o.price for o in option_objs)
        validated_data["options_price"] = opts_total
        validated_data["total_price"] = course.price + opts_total
        medium = validated_data.get("medium")
        if medium:
            validated_data["medium_name"] = medium.name
        order = Order.objects.create(**validated_data)
        for opt in option_objs:
            OrderOption.objects.get_or_create(order=order, option=opt)
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
        fields = ["cast", "course", "start", "end", "memo", "options"]

    def validate(self, data):
        instance = self.instance
        cast = data.get("cast", instance.cast)
        start = data.get("start", instance.start)
        end = data.get("end", instance.end)

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
            assignment = ShiftAssignment.objects.filter(
                store=store,
                date=start.date(),
                cast=cast,
                start_time__lte=start.time(),
                end_time__gte=end.time(),
            ).first()
            if assignment is None:
                raise serializers.ValidationError("このキャストは指定日時にシフトがありません")
            data["room"] = assignment.room

            # Cast conflict (exclude self)
            if Order.objects.filter(
                cast=cast,
                status__in=Order.ACTIVE_STATUSES,
                start__lt=end,
                end__gt=start,
            ).exclude(pk=instance.pk).exists():
                raise serializers.ValidationError("このキャストは指定時間に予約が入っています")

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

    class Meta:
        model = ShiftAssignment
        fields = ["id", "room_id", "room_name", "start_time", "end_time"]


class ScheduleCastSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    avatar_url = serializers.CharField()
    shifts = ScheduleShiftSerializer(many=True)


class ScheduleOrderSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    cast_id = serializers.IntegerField()
    room_id = serializers.IntegerField()
    customer_label = serializers.CharField()
    course_name = serializers.CharField()
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
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

    cast_data = []
    for c in casts:
        cast_data.append({
            "id": c.id,
            "name": c.name,
            "avatar_url": c.avatar_url,
            "shifts": shifts_by_cast.get(c.id, []),
        })

    orders = (
        Order.objects
        .filter(store=store, start__date=date)
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

    orders = (
        Order.objects
        .filter(store=store, start__date=date, room__isnull=False)
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
        "rooms": [{"id": r.id, "name": r.name, "sort_order": r.sort_order} for r in rooms],
        "orders": order_data,
        "kpi": kpi,
    }
