from django.contrib import admin
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from .models import (
    CallLog, CallNote, Cast, CastCheckoutExpenseSnapshot, CastDailyCheckout,
    CastExpense, CastExpenseTemplate,
    CastExpenseTemplateHistory, CastNote, Course, Customer, CustomerAccountInvitation, CustomerMergeLog,
    DailySettlement, LineNotificationLog, Option, Order, PointLog, Room,
    ShiftAssignment, ShiftConfirmNotificationLog, ShiftRequest, SmsLog, SmsTemplate, Store,
    StorePhoneNumber, UserProfile,
    generate_line_link_code,
)
from .services.cast_user import ensure_user_profile, create_staff_with_user


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "timezone", "line_is_enabled", "line_add_friend_url")
    fieldsets = (
        (None, {"fields": ("name", "timezone")}),
        ("LINE設定", {"fields": (
            "line_is_enabled",
            "line_channel_secret",
            "line_channel_access_token",
            "line_add_friend_url",
            "line_webhook_token",
        )}),
    )
    readonly_fields = ("line_webhook_token",)


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "name", "address", "sort_order")
    list_filter = ("store",)


@admin.register(Cast)
class CastAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "name", "age", "interval_minutes", "course_back_rate", "user", "line_link_code", "line_linked_at")
    list_filter = ("store",)
    readonly_fields = ("line_user_id", "line_linked_at", "line_unlink_button")

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
    list_display = ("id", "store", "phone", "display_name", "flag", "ban_type", "user")
    list_filter = ("store", "flag", "ban_type")
    search_fields = ("phone", "display_name")


@admin.register(CustomerAccountInvitation)
class CustomerAccountInvitationAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "order", "expires_at", "used_at", "invalidated_at", "created_at")
    list_filter = ("customer__store", "used_at", "invalidated_at")
    readonly_fields = (
        "customer", "order", "token_hash", "expires_at", "used_at",
        "invalidated_at", "created_by", "sms_log", "created_at",
    )
    search_fields = ("customer__phone", "customer__display_name")


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
        "id", "store", "cast", "customer", "service_recipient_name",
        "course", "start", "end", "status",
    )
    list_filter = ("store", "status")
    search_fields = (
        "customer__phone", "customer__display_name", "service_recipient_name",
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


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "store", "role")
    list_filter = ("store", "role")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.user:
            ensure_user_profile(obj.user, obj.store, role=obj.role)
