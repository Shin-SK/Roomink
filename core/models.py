import secrets
import string
import uuid

from django.conf import settings
from django.db import models


def generate_line_link_code():
    """6桁の英数字連携コードを生成"""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(6))


def generate_line_webhook_token():
    """Store 識別用 webhook パストークン (32文字 hex)"""
    return secrets.token_hex(16)


class Store(models.Model):
    name = models.CharField(max_length=100)
    timezone = models.CharField(max_length=40, default="Asia/Tokyo")
    line_add_friend_url = models.URLField(blank=True, default="")
    line_channel_secret = models.TextField(blank=True, default="")
    line_channel_access_token = models.TextField(blank=True, default="")
    line_is_enabled = models.BooleanField(default=False)
    line_morning_enabled = models.BooleanField(default=True)
    line_morning_time = models.TimeField(default="09:00")
    line_two_hours_enabled = models.BooleanField(default=True)
    line_fifteen_minutes_enabled = models.BooleanField(default=True)
    line_webhook_token = models.CharField(
        max_length=64, blank=True, default="", unique=True,
        help_text="webhook URL に埋め込む store 識別トークン",
    )

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.line_webhook_token:
            self.line_webhook_token = generate_line_webhook_token()
        super().save(*args, **kwargs)


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
    age = models.PositiveSmallIntegerField(null=True, blank=True, help_text="年齢")
    hp_url = models.URLField(blank=True, default="", help_text="HPのURL")
    staff_memo = models.TextField(blank=True, default="", help_text="運営専用メモ（manager/staffのみ閲覧可）")
    introduction = models.TextField(blank=True, default="", help_text="店側紹介用コメント（お客様マイページ表示用）")
    interval_minutes = models.PositiveSmallIntegerField(default=15, help_text="イ��ターバル時間（分）")
    course_back_rate = models.PositiveSmallIntegerField(default=0, help_text="コースバック率（%）")
    option_fullback_enabled = models.BooleanField(default=False, help_text="オプション全額バック")
    line_user_id = models.CharField(max_length=64, null=True, blank=True, unique=True)
    line_link_code = models.CharField(
        max_length=8, null=True, blank=True, unique=True,
        default=generate_line_link_code,
    )
    line_linked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("store", "name")

    def __str__(self):
        return self.name


class Customer(models.Model):
    class Flag(models.TextChoices):
        NONE = "NONE", "なし"
        BAN = "BAN", "出禁"
        ATTENTION = "ATTENTION", "要注意"

    class BanType(models.TextChoices):
        NONE = "NONE", "なし"
        STORE_BAN = "STORE_BAN", "店出禁"
        CAST_NG = "CAST_NG", "個別セラピNG"

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
    ban_type = models.CharField(
        max_length=12, choices=BanType.choices, default=BanType.NONE,
        help_text="出禁種別（flag=BAN 時に参照）",
    )
    memo = models.TextField(blank=True, default="")
    staff_memo = models.TextField(blank=True, default="", help_text="運営専用メモ（manager/staffのみ閲覧可）")

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
    target_casts = models.ManyToManyField(
        "Cast", blank=True, related_name="available_courses",
        help_text="表示対象キャスト（空なら全員に表示）",
    )

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

    class PaymentMethod(models.TextChoices):
        UNSET = "UNSET", "未設定"
        CARD = "CARD", "カード"
        CASH = "CASH", "現金"

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
    payment_method = models.CharField(
        max_length=10, choices=PaymentMethod.choices, default=PaymentMethod.UNSET,
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


class LineNotificationLog(models.Model):
    class NotificationType(models.TextChoices):
        MORNING = "MORNING", "朝通知"
        TWO_HOURS_BEFORE = "TWO_HOURS_BEFORE", "2時間前"
        FIFTEEN_MIN_BEFORE = "FIFTEEN_MIN_BEFORE", "15分前"

    class Status(models.TextChoices):
        SENT = "SENT", "送信済"
        FAILED = "FAILED", "失敗"
        SKIPPED = "SKIPPED", "スキップ"

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="line_notification_logs")
    cast = models.ForeignKey(Cast, on_delete=models.CASCADE, related_name="line_notification_logs")
    shift_assignment = models.ForeignKey(ShiftAssignment, on_delete=models.CASCADE, related_name="line_notification_logs")
    notification_type = models.CharField(max_length=20, choices=NotificationType.choices)
    status = models.CharField(max_length=10, choices=Status.choices)
    error_message = models.TextField(blank=True, default="")
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["store", "shift_assignment", "notification_type"]),
        ]

    def __str__(self):
        return f"LINE→{self.cast} {self.notification_type} {self.status}"


class CustomerMergeLog(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="merge_logs")
    keep_customer = models.ForeignKey(
        "Customer", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="merge_logs_as_keep",
    )
    merged_customer_id = models.IntegerField(help_text="削除された顧客の元ID")
    merged_customer_name = models.CharField(max_length=50, blank=True, default="")
    merged_customer_phone = models.CharField(max_length=20, blank=True, default="")
    orders_moved = models.PositiveIntegerField(default=0)
    call_logs_moved = models.PositiveIntegerField(default=0)
    executed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="executed_merges",
    )
    executed_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-executed_at"]

    def __str__(self):
        return f"Merge#{self.pk} keep={self.keep_customer_id} merged={self.merged_customer_id}"


class DailySettlement(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "未確定"
        LOCKED = "LOCKED", "確定済"

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="daily_settlements")
    date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    snapshot_json = models.JSONField(default=dict, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="locked_settlements",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("store", "date")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.store.name} {self.date} ({self.status})"


class PointLog(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="point_logs")
    cast = models.ForeignKey(Cast, on_delete=models.CASCADE, related_name="point_logs")
    date = models.DateField()
    points = models.IntegerField(help_text="正=加点 / 負=減点")
    reason = models.CharField(max_length=100, blank=True, default="")
    memo = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="created_point_logs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["store", "cast", "date"]),
        ]
        ordering = ["-date", "-created_at"]

    def __str__(self):
        sign = "+" if self.points >= 0 else ""
        return f"{self.cast.name} {self.date} {sign}{self.points}pt"


class CastExpense(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="cast_expenses")
    cast = models.ForeignKey(Cast, on_delete=models.CASCADE, related_name="expenses")
    date = models.DateField()
    name = models.CharField(max_length=50, help_text="名目（例: 雑費, 交通費, 備品代）")
    amount = models.PositiveIntegerField(help_text="金額（円）")
    per_order = models.BooleanField(default=False, help_text="True=予約件数×amount / False=日額amount")
    memo = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["store", "cast", "date"]),
        ]
        ordering = ["-date", "cast", "id"]

    def __str__(self):
        mode = "×件" if self.per_order else "日額"
        return f"{self.cast.name} {self.date} {self.name} ¥{self.amount}({mode})"


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
