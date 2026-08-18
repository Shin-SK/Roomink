import secrets
import string
import uuid

from django.conf import settings
from django.db import models


DAY_OFFSET_CHOICES = ((0, "当日"), (1, "翌日"))


def generate_line_link_code():
    """6桁の英数字連携コードを生成"""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(6))


def generate_line_webhook_token():
    """Store 識別用 webhook パストークン (32文字 hex)"""
    return secrets.token_hex(16)


def generate_line_operations_link_code():
    """運営通知先をLINEから登録するための使い切りコードを生成。"""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


def generate_store_slug():
    """設定前でも衝突しない店舗URL識別子を生成する。"""
    return f"store-{uuid.uuid4().hex[:12]}"


class Store(models.Model):
    class LineOperationsRecipientType(models.TextChoices):
        USER = "user", "個人トーク"
        GROUP = "group", "グループ"
        ROOM = "room", "複数人トーク"

    name = models.CharField(max_length=100)
    slug = models.SlugField(
        max_length=80,
        unique=True,
        default=generate_store_slug,
        help_text="顧客向けURLに使用する店舗識別子（例: rs-spa）",
    )
    timezone = models.CharField(max_length=40, default="Asia/Tokyo")
    line_add_friend_url = models.URLField(blank=True, default="")
    line_channel_secret = models.TextField(blank=True, default="")
    line_channel_access_token = models.TextField(blank=True, default="")
    line_is_enabled = models.BooleanField(default=False)
    line_morning_enabled = models.BooleanField(default=True)
    line_morning_time = models.TimeField(default="09:00")
    line_two_hours_enabled = models.BooleanField(default=True)
    line_fifteen_minutes_enabled = models.BooleanField(default=True)
    line_shift_end_alert_enabled = models.BooleanField(default=False)
    line_operations_recipient_id = models.CharField(max_length=64, blank=True, default="")
    line_operations_recipient_type = models.CharField(
        max_length=10,
        choices=LineOperationsRecipientType.choices,
        blank=True,
        default="",
    )
    line_operations_link_code = models.CharField(
        max_length=8,
        blank=True,
        default=generate_line_operations_link_code,
    )
    line_operations_linked_at = models.DateTimeField(null=True, blank=True)
    line_webhook_token = models.CharField(
        max_length=64, blank=True, default="", unique=True,
        help_text="webhook URL に埋め込む store 識別トークン",
    )
    # 決済手数料（参考値）。確定精算・給与確定には接続しない。
    cash_fee_rate = models.PositiveSmallIntegerField(default=0, help_text="現金決済手数料率（%・参考値）")
    paypay_fee_rate = models.PositiveSmallIntegerField(default=5, help_text="PayPay決済手数料率（%・参考値）")
    card_fee_rate = models.PositiveSmallIntegerField(default=10, help_text="カード決済手数料率（%・参考値）")
    public_booking_notice = models.TextField(
        blank=True,
        default="",
        help_text="店舗別のWeb予約画面へ表示する注意事項",
    )

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.line_webhook_token:
            self.line_webhook_token = generate_line_webhook_token()
        super().save(*args, **kwargs)

    @classmethod
    def resolve_slug(cls, slug):
        """現在または過去のslugから店舗を解決する。"""
        value = (slug or "").strip().lower()
        if not value:
            return None
        return (
            cls.objects.filter(slug=value).first()
            or cls.objects.filter(slug_aliases__slug=value).first()
        )


class StoreSlugAlias(models.Model):
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name="slug_aliases",
    )
    slug = models.SlugField(max_length=80, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.slug} -> {self.store.slug}"


class Room(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="rooms")
    name = models.CharField(max_length=50)
    address = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="予約確定後に顧客マイページへ表示する住所",
    )
    map_url = models.URLField(
        max_length=500,
        blank=True,
        default="",
        help_text="予約確認SMSへ掲載する地図URL",
    )
    sms_notice = models.TextField(
        blank=True,
        default="",
        help_text="予約確認SMSへ掲載するルーム固有の注意事項",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    background_color = models.CharField(max_length=7, blank=True, default="", help_text="HEX形式 例: #fde2e4")
    area_name = models.CharField(
        max_length=50, blank=True, default="",
        help_text="エリアタグ（例: 新宿・池袋・渋谷・五反田）。空欄可＝未設定扱い。",
    )

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
    preferred_area_1 = models.CharField(max_length=50, blank=True, default="", help_text="希望エリア 第1希望")
    preferred_area_2 = models.CharField(max_length=50, blank=True, default="", help_text="希望エリア 第2希望")
    preferred_area_3 = models.CharField(max_length=50, blank=True, default="", help_text="希望エリア 第3希望")
    preferred_area_4 = models.CharField(max_length=50, blank=True, default="", help_text="希望エリア 第4希望")
    preferred_area_5 = models.CharField(max_length=50, blank=True, default="", help_text="希望エリア 第5希望")
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
    email = models.EmailField(blank=True, default="")
    flag = models.CharField(max_length=12, choices=Flag.choices, default=Flag.NONE)
    ban_type = models.CharField(
        max_length=12, choices=BanType.choices, default=BanType.NONE,
        help_text="出禁種別（flag=BAN 時に参照）",
    )
    memo = models.TextField(blank=True, default="")
    staff_memo = models.TextField(blank=True, default="", help_text="運営専用メモ（manager/staffのみ閲覧可）")
    legacy_usage_history = models.TextField(
        blank=True,
        default="",
        help_text="旧システムから移行した利用履歴（参照用・売上集計対象外）",
    )

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
    end_day_offset = models.PositiveSmallIntegerField(
        choices=DAY_OFFSET_CHOICES,
        default=0,
        help_text="終了時刻がシフト日の翌日に属する場合は1",
    )
    clocked_in_at = models.DateTimeField(null=True, blank=True)
    daily_memo = models.TextField(blank=True, default="", help_text="その日だけのメモ")
    is_absent = models.BooleanField(default=False, help_text="当欠フラグ")
    confirmed_at = models.DateTimeField(
        null=True, blank=True,
        help_text="キャストによる出勤確認（事前）日時。Phase 3-B-1。clocked_in_at（実打刻）とは別概念。",
    )
    display_order = models.PositiveSmallIntegerField(
        default=0,
        help_text="タイムライン（キャスト別表示）の並び順。0=未設定で既存順（名前順）。シフト時間・部屋には影響しない。",
    )

    class Meta:
        unique_together = ("store", "date", "cast", "start_time", "end_time")
        indexes = [
            models.Index(fields=["store", "date"]),
        ]

    def __str__(self):
        return f"{self.cast} {self.date} {self.start_time}-{self.end_time}"


class CastUnavailableTime(models.Model):
    class Type(models.TextChoices):
        BREAK = "BREAK", "休憩"
        LATE = "LATE", "遅刻"
        EARLY_LEAVE = "EARLY_LEAVE", "早退"
        OUT = "OUT", "中抜け"
        STORE = "STORE", "店舗都合"
        OTHER = "OTHER", "その他"

    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name="cast_unavailable_times",
    )
    cast = models.ForeignKey(
        Cast,
        on_delete=models.CASCADE,
        related_name="unavailable_times",
    )
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    type = models.CharField(max_length=12, choices=Type.choices)
    memo = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_cast_unavailable_times",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_cast_unavailable_times",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["store", "cast", "start_at"]),
            models.Index(fields=["store", "start_at", "end_at"]),
        ]
        ordering = ["start_at", "id"]

    def __str__(self):
        return f"{self.cast} {self.get_type_display()} {self.start_at}-{self.end_at}"


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
    end_day_offset = models.PositiveSmallIntegerField(
        choices=DAY_OFFSET_CHOICES,
        default=0,
        help_text="終了時刻が申請日の翌日に属する場合は1",
    )
    desired_room = models.ForeignKey(Room, null=True, blank=True, on_delete=models.SET_NULL, related_name="shift_requests")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REQUESTED)
    memo = models.TextField(blank=True, default="")
    admin_memo = models.TextField(blank=True, default="")
    approved_date = models.DateField(null=True, blank=True)
    approved_start_time = models.TimeField(null=True, blank=True)
    approved_end_time = models.TimeField(null=True, blank=True)
    approved_end_day_offset = models.PositiveSmallIntegerField(
        choices=DAY_OFFSET_CHOICES,
        default=0,
        help_text="承認終了時刻が承認日の翌日に属する場合は1",
    )
    approved_room = models.ForeignKey(
        Room, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="approved_shift_requests",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="decided_shift_requests",
    )
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
        PENDING_FINALIZE = "PENDING_FINALIZE", "会計待ち"
        DONE = "DONE", "完了"
        CANCELLED = "CANCELLED", "キャンセル"

    class PaymentMethod(models.TextChoices):
        UNSET = "UNSET", "未設定"
        CARD = "CARD", "カード"
        CASH = "CASH", "現金"
        PAYPAY = "PAYPAY", "PayPay"

    ACTIVE_STATUSES = (
        Status.REQUESTED,
        Status.CONFIRMED,
        Status.IN_PROGRESS,
        Status.PENDING_FINALIZE,
    )

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="orders")
    cast = models.ForeignKey(Cast, on_delete=models.PROTECT, related_name="orders")
    room = models.ForeignKey(
        Room,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="orders",
        help_text="シフト外予約では未定のまま保存し、シフト登録時に割り当てる",
    )
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="orders")
    service_recipient_name = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="実際の利用者名。空欄は連絡者本人として扱う",
    )
    service_recipient_customer = models.ForeignKey(
        Customer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="service_recipient_orders",
        help_text="管理者が確認して紐付けた実利用者の顧客レコード",
    )
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
    extension_duration = models.PositiveIntegerField(default=0)
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
        max_length=20, choices=Status.choices, default=Status.REQUESTED,
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


class CustomerAccountInvitation(models.Model):
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="account_invitations",
    )
    order = models.ForeignKey(
        Order,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="customer_account_invitations",
    )
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_customer_account_invitations",
    )
    sms_log = models.ForeignKey(
        "SmsLog",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="customer_account_invitations",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["customer", "-created_at"]),
        ]

    def __str__(self):
        return f"CustomerAccountInvitation#{self.pk} customer={self.customer_id}"


class PublicBookingVerification(models.Model):
    """公開Web予約のSMS本人確認。予約・顧客は確認完了後にだけ作成する。"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name="public_booking_verifications",
    )
    phone = models.CharField(max_length=20)
    display_name = models.CharField(max_length=50)
    booking_payload = models.JSONField()
    code_hash = models.CharField(max_length=255)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    sms_log = models.ForeignKey(
        "SmsLog",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="public_booking_verifications",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["phone", "-created_at"],
                name="core_publi_phone_eb42af_idx",
            ),
            models.Index(
                fields=["expires_at"],
                name="core_publi_expires_c8e502_idx",
            ),
        ]

    def __str__(self):
        return f"PublicBookingVerification#{self.pk} store={self.store_id}"


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
    source_phone = models.CharField(max_length=20, blank=True, default="")
    label = models.CharField(max_length=50, blank=True, default="")
    memo = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

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


class SmsTemplate(models.Model):
    """店舗ごと・支払方法ごとのSMS文面テンプレート。
    未設定（レコード無し or is_active=False）の場合は notify.py の既定文言を使う。"""

    class TemplateType(models.TextChoices):
        RESERVATION_CONFIRMATION = "RESERVATION_CONFIRMATION", "予約確認"

    # 差し込み可能な変数（画面の「使用可能な差し込み項目」と対応）
    PLACEHOLDERS = (
        "customer_name", "date", "start_time", "end_time",
        "course_name", "cast_name", "room_name", "room_address",
        "room_map_url", "room_notice", "room_guidance",
        "payment_method", "discount_name", "discount_amount",
        "subtotal_price", "total_price",
    )

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="sms_templates")
    template_type = models.CharField(
        max_length=32, choices=TemplateType.choices,
        default=TemplateType.RESERVATION_CONFIRMATION,
    )
    payment_method = models.CharField(
        max_length=10, choices=Order.PaymentMethod.choices,
        default=Order.PaymentMethod.UNSET,
    )
    body = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=False, help_text="OFFの場合は既定文言を使用")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="updated_sms_templates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("store", "template_type", "payment_method")

    def __str__(self):
        return f"SmsTemplate({self.store_id}/{self.template_type}/{self.payment_method})"


class SmsLog(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "送信中"
        SENT = "SENT", "送信済"
        FAILED = "FAILED", "失敗"
        SKIPPED = "SKIPPED", "対象外"
        DUMMY = "DUMMY", "開発用ダミー"
        CONFIG_MISSING = "CONFIG_MISSING", "設定不足"

    class TemplateType(models.TextChoices):
        RESERVATION_CONFIRMATION = "RESERVATION_CONFIRMATION", "予約確認"
        RESERVATION_CANCELLED = "RESERVATION_CANCELLED", "予約キャンセル"
        CAST_NOTICE = "CAST_NOTICE", "キャスト通知"
        REMINDER = "REMINDER", "リマインド"
        OTHER = "OTHER", "その他"

    class Provider(models.TextChoices):
        TWILIO = "TWILIO", "Twilio"
        NONE = "NONE", "未送信（ダミー）"
        OTHER = "OTHER", "その他"

    store = models.ForeignKey(
        Store, on_delete=models.CASCADE, null=True, blank=True, related_name="sms_logs",
    )
    order = models.ForeignKey(
        Order, on_delete=models.SET_NULL, null=True, blank=True, related_name="sms_logs",
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name="sms_logs",
    )
    to_phone = models.CharField(max_length=20)
    body = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices)
    template_type = models.CharField(
        max_length=32, choices=TemplateType.choices, default=TemplateType.OTHER,
    )
    payment_method = models.CharField(
        max_length=10, choices=Order.PaymentMethod.choices, blank=True, default="",
    )
    provider = models.CharField(
        max_length=10, choices=Provider.choices, default=Provider.NONE,
    )
    provider_message_id = models.CharField(max_length=64, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="created_sms_logs",
    )
    # 既存フィールド。送信試行の記録日時として維持する（FAILED/SKIPPED でも記録される）。
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["order", "-sent_at"]),
        ]

    def __str__(self):
        return f"SMS→{self.to_phone} {self.status}"


class LineNotificationLog(models.Model):
    class NotificationType(models.TextChoices):
        MORNING = "MORNING", "朝通知"
        TWO_HOURS_BEFORE = "TWO_HOURS_BEFORE", "2時間前"
        FIFTEEN_MIN_BEFORE = "FIFTEEN_MIN_BEFORE", "15分前"
        SHIFT_END_70 = "SHIFT_END_70", "終了70分前"

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


class OrderServiceRecipientLinkLog(models.Model):
    """予約と実利用者顧客の手動紐付け監査ログ。"""

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="recipient_link_logs")
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="recipient_link_logs")
    previous_customer_id = models.PositiveIntegerField(null=True, blank=True)
    previous_customer_name = models.CharField(max_length=50, blank=True, default="")
    linked_customer_id = models.PositiveIntegerField(null=True, blank=True)
    linked_customer_name = models.CharField(max_length=50, blank=True, default="")
    executed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="executed_recipient_links",
    )
    executed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-executed_at", "-id"]

    def __str__(self):
        return f"Order#{self.order_id} recipient={self.linked_customer_id or '-'}"


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


class CastExpenseTemplate(models.Model):
    """キャスト別固定雑費テンプレ（日次実績ではなく、紐づく定常項目）"""
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="cast_expense_templates")
    cast = models.ForeignKey(Cast, on_delete=models.CASCADE, related_name="expense_templates")
    name = models.CharField(max_length=50, help_text="固定雑費名")
    amount = models.PositiveIntegerField()
    memo = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["cast", "-is_active", "id"]

    def __str__(self):
        return f"{self.cast.name} {self.name} ¥{self.amount}"


class CastExpenseTemplateHistory(models.Model):
    class Action(models.TextChoices):
        CREATE = "CREATE", "新規作成"
        UPDATE = "UPDATE", "更新"
        ACTIVATE = "ACTIVATE", "有効化"
        DEACTIVATE = "DEACTIVATE", "無効化"

    template = models.ForeignKey(
        CastExpenseTemplate, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="history",
    )
    cast = models.ForeignKey(
        Cast, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="expense_template_history",
    )
    name = models.CharField(max_length=50)
    amount = models.PositiveIntegerField()
    memo = models.TextField(blank=True, default="")
    is_active = models.BooleanField()
    action = models.CharField(max_length=10, choices=Action.choices)
    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="cast_expense_template_edits",
    )
    edited_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-edited_at"]

    def __str__(self):
        return f"{self.cast} {self.name} {self.action} {self.edited_at:%Y-%m-%d %H:%M}"


class CastDailyCheckout(models.Model):
    """キャスト退勤提出（Phase 3-A）。給与確定ではなく、退勤時点の見込みスナップショット+manager確認の土台。"""
    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "提出済"
        REVIEWED = "REVIEWED", "確認済"
        RETURNED = "RETURNED", "差戻し"

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="cast_daily_checkouts")
    cast = models.ForeignKey(Cast, on_delete=models.CASCADE, related_name="daily_checkouts")
    date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SUBMITTED)

    # 提出時点の見込みスナップショット（Order DONE 集計。CastTodaySalesViewと同じ計算方針）
    done_count = models.PositiveIntegerField(default=0)
    total_sales = models.PositiveIntegerField(default=0)
    estimated_pay = models.PositiveIntegerField(default=0)
    course_sales = models.PositiveIntegerField(default=0)
    options_sales = models.PositiveIntegerField(default=0)
    payment_fee_estimate = models.PositiveIntegerField(
        default=0, help_text="決済手数料見込み（参考値。給与確定・支払い処理には接続しない）",
    )
    net_sales_after_payment_fee = models.IntegerField(
        default=0, help_text="手数料差引後売上見込み（参考値）",
    )

    actual_take_home_amount = models.PositiveIntegerField(default=0, help_text="実際の持ち帰り金額（キャスト入力）")
    checklist_json = models.JSONField(default=dict, blank=True, help_text="退勤チェックリストの回答")
    cast_memo = models.TextField(blank=True, default="")
    manager_memo = models.TextField(blank=True, default="")

    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="cast_checkout_reviews",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("store", "cast", "date")
        indexes = [
            models.Index(fields=["store", "date"]),
        ]
        ordering = ["-date", "cast"]

    def __str__(self):
        return f"{self.cast.name} {self.date} ({self.status})"


class CastCheckoutExpenseSnapshot(models.Model):
    """退勤提出時点の固定雑費テンプレのスナップショット（テンプレ本体が後から変わっても金額を固定）"""
    checkout = models.ForeignKey(CastDailyCheckout, on_delete=models.CASCADE, related_name="expense_snapshots")
    template = models.ForeignKey(
        CastExpenseTemplate, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="checkout_snapshots",
    )
    name = models.CharField(max_length=50)
    amount = models.PositiveIntegerField()
    memo = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.checkout} {self.name} ¥{self.amount}"


class CastAdjustment(models.Model):
    """調整金台帳（Phase 3-E）。退勤精算や日々の運用で発生する調整金の未解消/解消管理のみを行う。
    給与確定・支払い処理・退勤提出の給与計算には一切接続しない。"""
    class Status(models.TextChoices):
        OPEN = "OPEN", "未解消"
        RESOLVED = "RESOLVED", "解消済"
        VOID = "VOID", "無効"

    class SourceType(models.TextChoices):
        MANUAL = "MANUAL", "手動"
        CHECKOUT = "CHECKOUT", "退勤提出"
        ORDER = "ORDER", "予約"
        OTHER = "OTHER", "その他"

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="cast_adjustments")
    cast = models.ForeignKey(Cast, on_delete=models.CASCADE, related_name="adjustments")
    date = models.DateField()
    amount = models.IntegerField(
        help_text="正=キャストへ追加で渡す金額 / 負=キャストから店へ戻す（差し引く）金額",
    )
    title = models.CharField(max_length=100)
    memo = models.TextField(blank=True, default="", help_text="マネージャーメモ（キャストにも表示される）")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    source_type = models.CharField(max_length=10, choices=SourceType.choices, default=SourceType.MANUAL)
    source_checkout = models.ForeignKey(
        CastDailyCheckout, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="adjustments",
    )
    source_order = models.ForeignKey(
        Order, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="adjustments",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="created_cast_adjustments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="resolved_cast_adjustments",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_memo = models.TextField(blank=True, default="", help_text="解消・無効化時のメモ")

    class Meta:
        indexes = [
            models.Index(fields=["store", "cast", "date"]),
            models.Index(fields=["store", "status"]),
        ]
        ordering = ["-date", "-created_at"]

    def __str__(self):
        sign = "+" if self.amount >= 0 else ""
        return f"{self.cast.name} {self.date} {self.title} {sign}{self.amount} ({self.status})"


class CastNote(models.Model):
    """店舗がキャスト向けに出す施術マニュアル/接客メモ/店舗ルール/連絡事項/お知らせ記事。
    既存のRoomink操作マニュアル機能（フロントエンド静的データ manualData.js）とは別物。
    manager が作成し、cast がマイページから閲覧する。"""
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "下書き"
        PUBLISHED = "PUBLISHED", "公開"
        ARCHIVED = "ARCHIVED", "アーカイブ"

    class Visibility(models.TextChoices):
        CAST = "CAST", "キャストのみ"
        STAFF = "STAFF", "スタッフのみ"
        ALL = "ALL", "全員"

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="cast_notes")
    title = models.CharField(max_length=100)
    category = models.CharField(max_length=50, blank=True, default="", help_text="カテゴリ（例: 施術マニュアル・接客メモ・店舗ルール・お知らせ）")
    body = models.TextField(blank=True, default="", help_text="本文（プレーンテキストまたは簡易Markdown）")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    is_pinned = models.BooleanField(default=False)
    visibility = models.CharField(max_length=10, choices=Visibility.choices, default=Visibility.CAST)
    video_url = models.URLField(
        blank=True, default="",
        help_text="将来の動画掲載用URL（今回はアップロード等は未実装。任意入力欄のみ）",
    )
    target_casts = models.ManyToManyField(
        Cast,
        blank=True,
        related_name="targeted_notes",
        help_text="指定なしの場合は全キャストへ公開",
    )
    image_urls = models.JSONField(
        blank=True,
        default=list,
        help_text="ノートへ添付する画像URL（表示順）",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="created_cast_notes",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="updated_cast_notes",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["store", "status", "is_pinned"]),
        ]
        ordering = ["-is_pinned", "-published_at", "-created_at"]

    def __str__(self):
        return f"{self.title} ({self.status})"


class ShiftConfirmNotificationLog(models.Model):
    """出勤確認アラートの外部通知の土台（Phase 4）。
    実送信は行わない。ログ作成のみで、通知チャネルの初期値は NONE。
    将来 LINE/SMS/メール等を有効化する際の記録先として用意する。"""
    class AlertLevel(models.TextChoices):
        TWO_HOURS = "TWO_HOURS", "2時間前"
        ONE_HOUR = "ONE_HOUR", "1時間前"

    class TargetType(models.TextChoices):
        CAST = "CAST", "キャスト"
        MANAGER = "MANAGER", "マネージャー"
        STAFF = "STAFF", "スタッフ"

    class Channel(models.TextChoices):
        NONE = "NONE", "未設定（実送信なし）"
        LINE = "LINE", "LINE"
        SMS = "SMS", "SMS"
        EMAIL = "EMAIL", "メール"

    class Status(models.TextChoices):
        PENDING = "PENDING", "送信予定"
        SENT = "SENT", "送信済"
        SKIPPED = "SKIPPED", "スキップ（テスト/実送信無効）"
        FAILED = "FAILED", "失敗"

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="shift_confirm_notification_logs")
    shift_assignment = models.ForeignKey(
        ShiftAssignment, on_delete=models.CASCADE, related_name="confirm_notification_logs",
    )
    cast = models.ForeignKey(Cast, on_delete=models.CASCADE, related_name="shift_confirm_notification_logs")
    alert_level = models.CharField(max_length=10, choices=AlertLevel.choices)
    target_type = models.CharField(max_length=10, choices=TargetType.choices, default=TargetType.CAST)
    channel = models.CharField(max_length=10, choices=Channel.choices, default=Channel.NONE)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    message = models.TextField(blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    sent_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="created_shift_confirm_notification_logs",
        help_text="テストログを作成したユーザー（手動作成の場合）",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["store", "shift_assignment", "alert_level"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.cast} {self.alert_level} {self.channel} {self.status}"


class ShiftEndAlert(models.Model):
    """シフト終了70分前の受付終了確認アラート。"""

    class Status(models.TextChoices):
        OPEN = "OPEN", "対応待ち"
        RESOLVED = "RESOLVED", "解消済み"

    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name="shift_end_alerts",
    )
    shift_assignment = models.OneToOneField(
        ShiftAssignment,
        on_delete=models.CASCADE,
        related_name="shift_end_alert",
    )
    cast = models.ForeignKey(
        Cast,
        on_delete=models.CASCADE,
        related_name="shift_end_alerts",
    )
    alert_at = models.DateTimeField()
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.OPEN,
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["store", "status"], name="core_sea_store_status_idx"),
            models.Index(fields=["alert_at"], name="core_sea_alert_at_idx"),
        ]
        ordering = ["-alert_at", "-id"]

    def __str__(self):
        return f"{self.cast} {self.alert_at} {self.status}"


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
