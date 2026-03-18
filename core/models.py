import uuid

from django.conf import settings
from django.db import models


class Store(models.Model):
    name = models.CharField(max_length=100)
    timezone = models.CharField(max_length=40, default="Asia/Tokyo")

    def __str__(self):
        return self.name


class Room(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="rooms")
    name = models.CharField(max_length=50)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = ("store", "name")
        ordering = ("sort_order",)

    def __str__(self):
        return self.name


class Cast(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="casts")
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="cast_profile",
    )
    name = models.CharField(max_length=50)
    avatar_url = models.URLField(blank=True, default="")

    class Meta:
        unique_together = ("store", "name")

    def __str__(self):
        return self.name


class Customer(models.Model):
    class Flag(models.TextChoices):
        NONE = "NONE", "なし"
        BAN = "BAN", "出禁"
        ATTENTION = "ATTENTION", "要注意"

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="customers")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="customer_profiles",
    )
    phone = models.CharField(max_length=20)
    display_name = models.CharField(max_length=50, blank=True, default="")
    flag = models.CharField(max_length=12, choices=Flag.choices, default=Flag.NONE)
    memo = models.TextField(blank=True, default="")

    class Meta:
        unique_together = ("store", "phone")

    def __str__(self):
        return self.display_name or self.phone


class ShiftAssignment(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="shift_assignments")
    date = models.DateField()
    cast = models.ForeignKey(Cast, on_delete=models.CASCADE, related_name="shift_assignments")
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="shift_assignments")
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        unique_together = ("store", "date", "cast", "start_time", "end_time")
        indexes = [
            models.Index(fields=["store", "date"]),
        ]

    def __str__(self):
        return f"{self.cast} {self.date} {self.start_time}-{self.end_time}"


class ShiftRequest(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "REQUESTED", "申請中"
        APPROVED = "APPROVED", "承認済"
        REJECTED = "REJECTED", "却下"
        CANCELLED = "CANCELLED", "取消"

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="shift_requests")
    cast = models.ForeignKey(Cast, on_delete=models.CASCADE, related_name="shift_requests")
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    desired_room = models.ForeignKey(Room, null=True, blank=True, on_delete=models.SET_NULL, related_name="shift_requests")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REQUESTED)
    memo = models.TextField(blank=True, default="")
    admin_memo = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["store", "date", "status"]),
        ]

    def __str__(self):
        return f"ShiftRequest#{self.pk} {self.cast} {self.date} {self.start_time}-{self.end_time} ({self.status})"


class Course(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="courses")
    name = models.CharField(max_length=50)
    duration = models.PositiveIntegerField(help_text="分")
    price = models.PositiveIntegerField()

    def __str__(self):
        return self.name


class Option(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="options")
    name = models.CharField(max_length=50)
    price = models.PositiveIntegerField()

    def __str__(self):
        return self.name


class Extension(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="extensions")
    name = models.CharField(max_length=50)
    duration = models.PositiveIntegerField(help_text="分")
    price = models.PositiveIntegerField()
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("sort_order", "id")

    def __str__(self):
        return self.name


class NominationFee(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="nomination_fees")
    name = models.CharField(max_length=50)
    price = models.PositiveIntegerField()
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("sort_order", "id")

    def __str__(self):
        return self.name


class Discount(models.Model):
    class DiscountType(models.TextChoices):
        FIXED = "fixed", "固定額"
        PERCENT = "percent", "パーセント"

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="discounts")
    name = models.CharField(max_length=50)
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices, default=DiscountType.FIXED)
    value = models.PositiveIntegerField()
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("sort_order", "id")

    def __str__(self):
        return self.name


class Medium(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="media")
    name = models.CharField(max_length=50)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("sort_order", "id")

    def __str__(self):
        return self.name


class Order(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "REQUESTED", "リクエスト"
        CONFIRMED = "CONFIRMED", "確定"
        IN_PROGRESS = "IN_PROGRESS", "施術中"
        DONE = "DONE", "完了"
        CANCELLED = "CANCELLED", "キャンセル"

    ACTIVE_STATUSES = (
        Status.REQUESTED,
        Status.CONFIRMED,
        Status.IN_PROGRESS,
    )

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="orders")
    cast = models.ForeignKey(Cast, on_delete=models.PROTECT, related_name="orders")
    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name="orders")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="orders")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="orders")
    options = models.ManyToManyField("Option", through="OrderOption", blank=True)
    extension = models.ForeignKey(
        "Extension", null=True, blank=True, on_delete=models.SET_NULL, related_name="orders",
    )
    nomination_fee = models.ForeignKey(
        "NominationFee", null=True, blank=True, on_delete=models.SET_NULL, related_name="orders",
    )
    discount = models.ForeignKey(
        "Discount", null=True, blank=True, on_delete=models.SET_NULL, related_name="orders",
    )
    medium = models.ForeignKey(
        "Medium", null=True, blank=True, on_delete=models.SET_NULL, related_name="orders",
    )
    course_name = models.CharField(max_length=50, default="")
    course_price = models.PositiveIntegerField(default=0)
    options_price = models.PositiveIntegerField(default=0)
    extension_name = models.CharField(max_length=50, default="")
    extension_price = models.PositiveIntegerField(default=0)
    nomination_fee_name = models.CharField(max_length=50, default="")
    nomination_fee_price = models.PositiveIntegerField(default=0)
    discount_name = models.CharField(max_length=50, default="")
    discount_type_snapshot = models.CharField(max_length=10, default="")
    discount_value_snapshot = models.PositiveIntegerField(default=0)
    discount_amount = models.PositiveIntegerField(default=0)
    medium_name = models.CharField(max_length=50, default="")
    total_price = models.PositiveIntegerField(default=0)
    start = models.DateTimeField()
    end = models.DateTimeField()
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.REQUESTED,
    )
    memo = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["store", "cast", "start"]),
            models.Index(fields=["store", "room", "start"]),
        ]

    def __str__(self):
        return f"Order#{self.pk} {self.cast} {self.start:%m/%d %H:%M}"


class OrderOption(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    option = models.ForeignKey(Option, on_delete=models.PROTECT)

    class Meta:
        unique_together = ("order", "option")


class CastAck(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="cast_ack")
    acked_at = models.DateTimeField(null=True, blank=True)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    def __str__(self):
        status = "ACK" if self.acked_at else "PENDING"
        return f"CastAck#{self.pk} {status}"


class StorePhoneNumber(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="phone_numbers")
    phone = models.CharField(max_length=20, unique=True)
    label = models.CharField(max_length=50, blank=True, default="")

    def __str__(self):
        return f"{self.store.name} - {self.phone}"


class CallLog(models.Model):
    class Status(models.TextChoices):
        NEW = "NEW", "新規"
        IN_PROGRESS = "IN_PROGRESS", "対応中"
        DONE = "DONE", "完了"
        MISSED = "MISSED", "不在"

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="call_logs")
    contact_id = models.CharField(max_length=128, unique=True)
    from_phone = models.CharField(max_length=20)
    to_phone = models.CharField(max_length=20)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_calls",
    )
    customer = models.ForeignKey(
        Customer, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="call_logs",
    )
    is_repeat = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["store", "status", "created_at"]),
            models.Index(fields=["store", "from_phone", "created_at"]),
        ]

    def __str__(self):
        return f"Call#{self.pk} {self.from_phone} → {self.to_phone} ({self.status})"


class CallNote(models.Model):
    call = models.ForeignKey(CallLog, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="call_notes",
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Note#{self.pk} on Call#{self.call_id}"


class SmsLog(models.Model):
    class Status(models.TextChoices):
        SENT = "SENT", "送信済"
        FAILED = "FAILED", "失敗"

    order = models.ForeignKey(
        Order, on_delete=models.SET_NULL, null=True, blank=True, related_name="sms_logs",
    )
    to_phone = models.CharField(max_length=20)
    body = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices)
    sent_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"SMS→{self.to_phone} {self.status}"


class UserProfile(models.Model):
    class Role(models.TextChoices):
        CAST = "cast", "キャスト"
        STAFF = "staff", "スタッフ"
        MANAGER = "manager", "マネージャー"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    store = models.ForeignKey(
        Store, on_delete=models.CASCADE, related_name="user_profiles",
    )
    role = models.CharField(
        max_length=10, choices=Role.choices, default=Role.STAFF,
    )
    avatar_url = models.URLField(blank=True, default="")

    def __str__(self):
        return f"Profile({self.user.username})"
