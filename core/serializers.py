from datetime import timedelta
from collections import defaultdict

from django.db.models import Sum
from rest_framework import serializers

from .utils.phone import normalize_phone
from .models import (
    Cast,
    CastAck,
    Course,
    Customer,
    Option,
    Order,
    OrderOption,
    Room,
    ShiftAssignment,
    Store,
)


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


class CastSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cast
        fields = "__all__"


class CustomerSerializer(serializers.ModelSerializer):
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


class OptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Option
        fields = "__all__"


# ──────────────────────────────────────
# ShiftAssignment (with overlap guard)
# ──────────────────────────────────────

class ShiftAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShiftAssignment
        fields = "__all__"

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
    course_name = serializers.CharField(source="course.name", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "store", "cast", "room", "customer", "course",
            "course_name", "customer_label",
            "start", "end", "status", "options", "memo",
            "created_at", "updated_at",
        ]

    def get_customer_label(self, obj):
        return build_customer_label(obj.customer)

    def get_options(self, obj):
        return list(obj.options.values_list("name", flat=True))


# ──────────────────────────────────────
# Order — create
# ──────────────────────────────────────

class OrderCreateSerializer(serializers.ModelSerializer):
    options = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Option.objects.all(), required=False,
    )

    class Meta:
        model = Order
        fields = [
            "cast", "customer", "course", "start", "end",
            "memo", "options",
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
    class Meta:
        model = Order
        fields = ["cast", "start", "end", "memo"]

    def validate(self, data):
        instance = self.instance
        cast = data.get("cast", instance.cast)
        start = data.get("start", instance.start)
        end = data.get("end", instance.end)

        time_or_cast_changed = "cast" in data or "start" in data or "end" in data
        if not time_or_cast_changed:
            return data

        if end <= start:
            raise serializers.ValidationError("終了時刻は開始時刻より後にしてください")

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
            "course_name": o.course.name,
            "start": o.start,
            "end": o.end,
            "status": o.status,
            "options": list(o.options.values_list("name", flat=True)),
            "is_unconfirmed": o.id not in acked_order_ids,
        })

    active_orders = [o for o in orders if o.status in Order.ACTIVE_STATUSES]
    estimated_sales = 0
    for o in active_orders:
        estimated_sales += o.course.price
        estimated_sales += (
            o.options.aggregate(total=Sum("price"))["total"] or 0
        )

    kpi = {
        "total_orders": orders.count(),
        "confirmed": sum(1 for o in orders if o.status == Order.Status.CONFIRMED),
        "requested": sum(1 for o in orders if o.status == Order.Status.REQUESTED),
        "estimated_sales": estimated_sales,
    }

    return {
        "date": date,
        "store_id": store.id,
        "casts": cast_data,
        "orders": order_data,
        "kpi": kpi,
    }
