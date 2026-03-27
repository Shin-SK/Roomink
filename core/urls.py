from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("orders", views.OrderViewSet)
router.register("shifts", views.ShiftAssignmentViewSet)
router.register("customers", views.CustomerViewSet)
router.register("casts", views.CastViewSet)
router.register("courses", views.CourseViewSet)
router.register("options", views.OptionViewSet)
router.register("rooms", views.RoomViewSet)
router.register("extensions", views.ExtensionViewSet)
router.register("nomination-fees", views.NominationFeeViewSet)
router.register("discounts", views.DiscountViewSet)
router.register("media", views.MediumViewSet)
router.register("staffs", views.StaffViewSet, basename="staff")

cast_sr_router = DefaultRouter()
cast_sr_router.register("shift-requests", views.CastShiftRequestViewSet, basename="cast-shift-request")

op_sr_router = DefaultRouter()
op_sr_router.register("shift-requests", views.OpShiftRequestViewSet, basename="op-shift-request")

urlpatterns = [
    # auth
    path("auth/csrf/", views.csrf_token_view, name="auth-csrf"),
    path("auth/login/", views.auth_login, name="auth-login"),
    path("auth/logout/", views.auth_logout, name="auth-logout"),
    path("auth/me/", views.auth_me, name="auth-me"),
    path("auth/profile/", views.auth_profile_update, name="auth-profile-update"),

    # cast
    path("cast/today/", views.CastTodayView.as_view(), name="cast-today"),
    path("cast/orders/<int:pk>/ack/", views.CastAckView.as_view(), name="cast-ack"),
    path("cast/line-link/", views.CastLineLinkView.as_view(), name="cast-line-link"),
    path("cast/", include(cast_sr_router.urls)),

    # customer
    path("cu/store-list/", views.StoreListPublicView.as_view(), name="cu-store-list"),
    path("cu/stores/", views.CustomerStoresView.as_view(), name="cu-stores"),
    path("cu/signup/", views.customer_signup, name="cu-signup"),
    path("cu/mypage/", views.CustomerMypageView.as_view(), name="cu-mypage"),
    path("cu/available-slots/", views.CustomerAvailableSlotsView.as_view(), name="cu-available-slots"),
    path("cu/booking/options/", views.CustomerBookingOptionsView.as_view(), name="cu-booking-options"),
    path("cu/bookings/", views.CustomerBookingCreateView.as_view(), name="cu-bookings"),
    path("cu/reservations/<int:pk>/", views.CustomerReservationDetailView.as_view(), name="cu-reservation-detail"),

    # operator
    path("op/schedule/", views.ScheduleView.as_view(), name="op-schedule"),
    path("op/room-schedule/", views.RoomScheduleView.as_view(), name="op-room-schedule"),
path("op/csv-import/", views.CsvImportView.as_view(), name="csv-import"),
    path("op/sales-summary/", views.SalesSummaryView.as_view(), name="sales-summary"),
    path("op/sales-export.csv", views.SalesExportView.as_view(), name="sales-export"),
    path("op/line-alerts/", views.LineAlertsView.as_view(), name="line-alerts"),
    path("op/", include(op_sr_router.urls)),

    # Twilio webhook
    path("webhook/twilio/voice/", views.twilio_voice_webhook, name="twilio-voice-webhook"),
    path("webhook/twilio/status/", views.twilio_status_webhook, name="twilio-status-webhook"),

    # LINE webhook
    path("webhook/line/", views.line_webhook, name="line-webhook"),
    path("webhook/line/<str:webhook_token>/", views.line_webhook_store, name="line-webhook-store"),

    # CTI
    path("op/cti/inbound/", views.CtiInboundView.as_view(), name="cti-inbound"),
    path("op/cti/queue/", views.CtiQueueView.as_view(), name="cti-queue"),
    path("op/cti/calls/<int:pk>/start/", views.CtiCallStartView.as_view(), name="cti-call-start"),
    path("op/cti/calls/<int:pk>/done/", views.CtiCallDoneView.as_view(), name="cti-call-done"),
    path("op/cti/calls/<int:pk>/notes/", views.CtiCallNoteView.as_view(), name="cti-call-notes"),

    # router (orders, shifts, customers, casts, courses, options, rooms)
    path("", include(router.urls)),
]
