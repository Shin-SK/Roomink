from django.contrib import admin

from .models import (
    CallLog, CallNote, Cast, Course, Customer, Option, Order,
    Room, ShiftAssignment, ShiftRequest, SmsLog, Store, StorePhoneNumber,
)


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "timezone")


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "name", "sort_order")
    list_filter = ("store",)


@admin.register(Cast)
class CastAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "name", "user")
    list_filter = ("store",)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "phone", "display_name", "flag", "user")
    list_filter = ("store", "flag")
    search_fields = ("phone", "display_name")


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "name", "duration", "price")
    list_filter = ("store",)


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
    list_display = ("id", "store", "date", "cast", "desired_room", "start_time", "end_time", "status", "created_at")
    list_filter = ("store", "status", "date")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "cast", "customer", "course", "start", "end", "status")
    list_filter = ("store", "status")


@admin.register(StorePhoneNumber)
class StorePhoneNumberAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "phone", "label")
    list_filter = ("store",)
    search_fields = ("phone",)


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
    list_display = ("id", "order", "to_phone", "status", "sent_at")
