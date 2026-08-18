from django.contrib import admin
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from .models import (
    CallLog, CallNote, Cast, CastCheckoutExpenseSnapshot, CastDailyCheckout,
    CastExpense, CastExpenseTemplate,
    CastExpenseTemplateHistory, CastNote, Course, Customer, CustomerAccountInvitation, CustomerMergeLog,
    DailySettlement, LineNotificationLog, Option, Order, OrderServiceRecipientLinkLog, PointLog, PublicBookingVerification, Room,
    ShiftAssignment, ShiftConfirmNotificationLog, ShiftEndAlert, ShiftRequest, SmsLog, SmsTemplate, Store, StoreSlugAlias,
    StorePhoneNumber, UserProfile,
    generate_line_link_code,
)
from .services.cast_user import ensure_user_profile, create_staff_with_user


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug", "timezone", "line_is_enabled", "line_add_friend_url")
    fieldsets = (
        (None, {"fields": ("name", "slug", "timezone")}),
        ("LINE設定", {"fields": (
            "line_is_enabled",
            "line_channel_secret",
            "line_channel_access_token",
            "line_add_friend_url",
            "line_webhook_token",
            "line_shift_end_alert_enabled",
            "line_operations_recipient_id",
            "line_operations_recipient_type",
            "line_operations_link_code",
            "line_operations_linked_at",
        )}),
    )
    readonly_fields = ("line_webhook_token", "line_operations_linked_at")


@admin.register(StoreSlugAlias)
class StoreSlugAliasAdmin(admin.ModelAdmin):
    list_display = ("slug", "store", "created_at")
    list_filter = ("store",)
    readonly_fields = ("created_at",)


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "name", "address", "sort_order")
    list_filter = ("store",)


@admin.register(Cast)
class CastAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "name", "preferred_areas_display", "age", "interval_minutes", "course_back_rate", "user", "line_link_code", "line_linked_at")
    list_filter = ("store",)
    readonly_fields = ("line_user_id", "line_linked_at", "line_unlink_button")

    @admin.display(description="希望エリア")
    def preferred_areas_display(self, obj):
        values = [
            getattr(obj, f"preferred_area_{rank}")
            for rank in range(1, 6)
            if getattr(obj, f"preferred_area_{rank}")
        ]
        return " ＞ ".join(values) or "-"

    def line_unlink_button(self, obj):
        if not obj.pk or not obj.line_user_id:
            return "-"
        url = reverse("admin:core_cast_line_unlink", args=[obj.pk])
        return format_html(
            '<a class="button" style="background:#ba2121;color:#fff;padding:4px 12px;border-radius:4px;text-decoration:none" '
            'href="{}">LINE連携を解除する</a>',
            url,
        )
    line_unlink_button.short_description = "LINE連携解除"

    def get_urls(self):
        custom = [
            path(
                "<path:object_id>/line-unlink/",
                self.admin_site.admin_view(self.line_unlink_view),
                name="core_cast_line_unlink",
            ),
        ]
        return custom + super().get_urls()

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.user:
            ensure_user_profile(obj.user, obj.store, role=UserProfile.Role.CAST)

    def line_unlink_view(self, request, object_id):
        cast = self.get_object(request, object_id)
        if cast is None:
            return HttpResponseRedirect(reverse("admin:core_cast_changelist"))

        if request.method == "POST":
            old_uid = cast.line_user_id
            cast.line_user_id = None
            cast.line_linked_at = None
            cast.line_link_code = generate_line_link_code()
            cast.save(update_fields=["line_user_id", "line_linked_at", "line_link_code"])
            self.message_user(
                request,
                f"{cast.name} の LINE連携を解除しました（旧 userId: {old_uid}）。新しい連携コード: {cast.line_link_code}",
            )
            return HttpResponseRedirect(
                reverse("admin:core_cast_change", args=[cast.pk])
            )

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "cast": cast,
            "title": f"LINE連携解除: {cast.name}",
        }
        return TemplateResponse(request, "admin/core/cast/line_unlink_confirm.html", context)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "phone", "display_name", "email", "flag", "ban_type", "user")
    list_filter = ("store", "flag", "ban_type")
    search_fields = ("phone", "display_name", "email", "legacy_usage_history")


@admin.register(CustomerAccountInvitation)
class CustomerAccountInvitationAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "order", "expires_at", "used_at", "invalidated_at", "created_at")
    list_filter = ("customer__store", "used_at", "invalidated_at")
    readonly_fields = (
        "customer", "order", "token_hash", "expires_at", "used_at",
        "invalidated_at", "created_by", "sms_log", "created_at",
    )
    search_fields = ("customer__phone", "customer__display_name")


@admin.register(PublicBookingVerification)
class PublicBookingVerificationAdmin(admin.ModelAdmin):
    list_display = (
        "id", "store", "masked_phone", "expires_at", "consumed_at",
        "failed_attempts", "created_at",
    )
    list_filter = ("store", "consumed_at")
    readonly_fields = (
        "id", "store", "phone", "display_name", "booking_payload", "code_hash",
        "failed_attempts", "expires_at", "consumed_at", "sms_log", "created_at",
    )

    @admin.display(description="電話番号")
    def masked_phone(self, obj):
        return f"***{obj.phone[-4:]}" if obj.phone else "***"


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "name", "duration", "price")
    list_filter = ("store",)
    filter_horizontal = ("target_casts",)


@admin.register(Option)
class OptionAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "name", "price")
    list_filter = ("store",)


@admin.register(ShiftAssignment)
class ShiftAssignmentAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "date", "cast", "room", "start_time", "end_time")
    list_filter = ("store", "date")


@admin.register(ShiftRequest)
class ShiftRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id", "store", "date", "cast", "desired_room", "start_time", "end_time",
        "status", "approved_date", "approved_room", "decided_by", "decided_at", "created_at",
    )
    list_filter = ("store", "status", "date")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id", "store", "cast", "customer", "service_recipient_name", "service_recipient_customer",
        "course", "start", "end", "status",
    )
    list_filter = ("store", "status")
    search_fields = (
        "customer__phone", "customer__display_name", "service_recipient_name",
        "service_recipient_customer__phone", "service_recipient_customer__display_name",
    )


@admin.register(OrderServiceRecipientLinkLog)
class OrderServiceRecipientLinkLogAdmin(admin.ModelAdmin):
    list_display = (
        "id", "store", "order", "previous_customer_id", "previous_customer_name",
        "linked_customer_id", "linked_customer_name", "executed_by", "executed_at",
    )
    list_filter = ("store",)
    readonly_fields = (
        "store", "order", "previous_customer_id", "previous_customer_name",
        "linked_customer_id", "linked_customer_name", "executed_by", "executed_at",
    )


@admin.register(StorePhoneNumber)
class StorePhoneNumberAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "phone", "source_phone", "label", "is_active")
    list_filter = ("store", "is_active")
    search_fields = ("phone", "source_phone")


class CallNoteInline(admin.TabularInline):
    model = CallNote
    extra = 0
    readonly_fields = ("author", "body", "created_at")


@admin.register(CallLog)
class CallLogAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "contact_id", "from_phone", "to_phone", "status", "customer", "is_repeat", "created_at")
    list_filter = ("store", "status", "is_repeat")
    search_fields = ("from_phone", "to_phone", "contact_id")
    inlines = [CallNoteInline]


@admin.register(CallNote)
class CallNoteAdmin(admin.ModelAdmin):
    list_display = ("id", "call", "author", "created_at")


@admin.register(SmsLog)
class SmsLogAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "to_phone", "template_type", "status", "sent_at")
    list_filter = ("store", "status", "template_type")


@admin.register(SmsTemplate)
class SmsTemplateAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "template_type", "payment_method", "is_active", "updated_at")
    list_filter = ("store", "template_type", "payment_method", "is_active")


@admin.register(LineNotificationLog)
class LineNotificationLogAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "cast", "notification_type", "status", "sent_at")
    list_filter = ("store", "status", "notification_type")
    search_fields = ("cast__name",)
    readonly_fields = ("store", "cast", "shift_assignment", "notification_type", "status", "error_message", "sent_at")


@admin.register(CustomerMergeLog)
class CustomerMergeLogAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "keep_customer", "merged_customer_id", "merged_customer_name", "merged_customer_phone", "orders_moved", "call_logs_moved", "executed_by", "executed_at")
    list_filter = ("store",)
    readonly_fields = ("store", "keep_customer", "merged_customer_id", "merged_customer_name", "merged_customer_phone", "orders_moved", "call_logs_moved", "executed_by", "executed_at")
    search_fields = ("merged_customer_name", "merged_customer_phone")


@admin.register(DailySettlement)
class DailySettlementAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "date", "status", "locked_at", "locked_by")
    list_filter = ("store", "status")
    readonly_fields = ("snapshot_json",)


@admin.register(PointLog)
class PointLogAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "cast", "date", "points", "reason", "created_by")
    list_filter = ("store", "date")
    search_fields = ("cast__name", "reason")


@admin.register(CastExpense)
class CastExpenseAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "cast", "date", "name", "amount", "per_order")
    list_filter = ("store", "date", "per_order")
    search_fields = ("cast__name", "name")


@admin.register(CastExpenseTemplate)
class CastExpenseTemplateAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "cast", "name", "amount", "is_active", "updated_at")
    list_filter = ("store", "is_active")
    search_fields = ("cast__name", "name")


@admin.register(CastExpenseTemplateHistory)
class CastExpenseTemplateHistoryAdmin(admin.ModelAdmin):
    list_display = ("id", "cast", "name", "amount", "is_active", "action", "edited_by", "edited_at")
    list_filter = ("action",)
    search_fields = ("cast__name", "name")


class CastCheckoutExpenseSnapshotInline(admin.TabularInline):
    model = CastCheckoutExpenseSnapshot
    extra = 0
    readonly_fields = ("template", "name", "amount", "memo", "created_at")
    can_delete = False


@admin.register(CastDailyCheckout)
class CastDailyCheckoutAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "cast", "date", "status", "total_sales", "estimated_pay", "actual_take_home_amount", "submitted_at", "reviewed_by")
    list_filter = ("store", "status", "date")
    search_fields = ("cast__name",)
    inlines = [CastCheckoutExpenseSnapshotInline]


@admin.register(CastNote)
class CastNoteAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "title", "category", "status", "is_pinned", "visibility", "published_at", "updated_at")
    list_filter = ("store", "status", "visibility", "is_pinned")
    search_fields = ("title", "body", "category")


@admin.register(ShiftConfirmNotificationLog)
class ShiftConfirmNotificationLogAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "cast", "alert_level", "target_type", "channel", "status", "created_at")
    list_filter = ("store", "alert_level", "target_type", "channel", "status")
    search_fields = ("cast__name",)
    readonly_fields = ("store", "shift_assignment", "cast", "alert_level", "target_type", "channel", "status", "message", "error_message", "sent_at", "created_by", "created_at")


@admin.register(ShiftEndAlert)
class ShiftEndAlertAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "cast", "shift_assignment", "alert_at", "status", "resolved_at")
    list_filter = ("store", "status")
    search_fields = ("cast__name",)
    readonly_fields = (
        "store", "shift_assignment", "cast", "alert_at", "status",
        "resolved_at", "created_at", "updated_at",
    )


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "store", "role")
    list_filter = ("store", "role")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.user:
            ensure_user_profile(obj.user, obj.store, role=obj.role)
