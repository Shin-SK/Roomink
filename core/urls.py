from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import support_views, views

router = DefaultRouter()
router.register("orders", views.OrderViewSet)
router.register("shifts", views.ShiftAssignmentViewSet)
router.register("cast-unavailable-times", views.CastUnavailableTimeViewSet, basename="cast-unavailable-time")
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
router.register("cast-expenses", views.CastExpenseViewSet, basename="cast-expense")
router.register("cast-expense-templates", views.CastExpenseTemplateViewSet, basename="cast-expense-template")
router.register("cast-expense-template-histories", views.CastExpenseTemplateHistoryViewSet, basename="cast-expense-template-history")
router.register("point-logs", views.PointLogViewSet, basename="point-log")
router.register("cast-checkouts", views.CastCheckoutViewSet, basename="cast-checkout")
router.register("cast-adjustments", views.CastAdjustmentViewSet, basename="cast-adjustment")
router.register("cast-notes", views.CastNoteViewSet, basename="cast-note")
router.register("shift-confirm-notification-logs", views.ShiftConfirmNotificationLogViewSet, basename="shift-confirm-notification-log")

cast_sr_router = DefaultRouter()
cast_sr_router.register("shift-requests", views.CastShiftRequestViewSet, basename="cast-shift-request")

op_sr_router = DefaultRouter()
op_sr_router.register("shift-requests", views.OpShiftRequestViewSet, basename="op-shift-request")
op_sr_router.register("call-logs", views.CallLogViewSet, basename="op-call-log")
op_sr_router.register("store-phones", views.StorePhoneNumberViewSet, basename="op-store-phone")

urlpatterns = [
    # auth
    path("auth/csrf/", views.csrf_token_view, name="auth-csrf"),
    path("auth/login/", views.auth_login, name="auth-login"),
    path("auth/logout/", views.auth_logout, name="auth-logout"),
    path("auth/password-reset/", views.auth_password_reset, name="auth-password-reset"),
    path("auth/me/", views.auth_me, name="auth-me"),
    path("auth/profile/", views.auth_profile_update, name="auth-profile-update"),

    # in-app support assistant
    path("support/chat/", support_views.SupportChatView.as_view(), name="support-chat"),
    path(
        "support/feature-requests/",
        support_views.SupportFeatureRequestView.as_view(),
        name="support-feature-request",
    ),
    path(
        "support/conversations/<int:conversation_id>/resolve/",
        support_views.SupportConversationResolveView.as_view(),
        name="support-conversation-resolve",
    ),
    path(
        "support/conversations/<int:conversation_id>/unresolved/",
        support_views.SupportConversationUnresolvedView.as_view(),
        name="support-conversation-unresolved",
    ),
    path(
        "support/conversations/<int:conversation_id>/escalate/",
        support_views.SupportConversationEscalateView.as_view(),
        name="support-conversation-escalate",
    ),
    path(
        "support/conversations/",
        support_views.MySupportConversationListView.as_view(),
        name="my-support-conversation-list",
    ),
    path(
        "support/conversations/<int:conversation_id>/",
        support_views.MySupportConversationDetailView.as_view(),
        name="my-support-conversation-detail",
    ),
    path(
        "op/support/conversations/",
        support_views.SupportConversationListView.as_view(),
        name="support-conversation-list",
    ),
    path(
        "op/support/conversations/<int:conversation_id>/",
        support_views.SupportConversationDetailView.as_view(),
        name="support-conversation-detail",
    ),
    path(
        "op/support/conversations/<int:conversation_id>/reply/",
        support_views.SupportConversationReplyView.as_view(),
        name="support-conversation-reply",
    ),
    path(
        "op/support/conversations/<int:conversation_id>/cancel-auto-reply/",
        support_views.SupportConversationCancelAutoReplyView.as_view(),
        name="support-conversation-cancel-auto-reply",
    ),

    # cast
    path("cast/today/", views.CastTodayView.as_view(), name="cast-today"),
    path("cast/today-sales/", views.CastTodaySalesView.as_view(), name="cast-today-sales"),
    path("cast/checkout/", views.CastCheckoutView.as_view(), name="cast-checkout"),
    path("cast/shift-confirm/", views.CastShiftConfirmView.as_view(), name="cast-shift-confirm"),
    path("cast/orders/<int:pk>/ack/", views.CastAckView.as_view(), name="cast-ack"),
    path("cast/line-link/", views.CastLineLinkView.as_view(), name="cast-line-link"),
    path("cast/points/", views.CastPointSummaryView.as_view(), name="cast-points"),
    path("cast/adjustments/", views.CastAdjustmentListView.as_view(), name="cast-adjustments"),
    path("cast/notes/", views.CastNoteListView.as_view(), name="cast-notes"),
    path("cast/", include(cast_sr_router.urls)),

    # customer
    path("cu/store-list/", views.StoreListPublicView.as_view(), name="cu-store-list"),
    path("public/booking/options/", views.PublicBookingOptionsView.as_view(), name="public-booking-options"),
    path("public/booking/slots/", views.PublicBookingSlotsView.as_view(), name="public-booking-slots"),
    path(
        "public/booking/request-verification/",
        views.PublicBookingVerificationRequestView.as_view(),
        name="public-booking-request-verification",
    ),
    path("public/booking/confirm/", views.PublicBookingConfirmView.as_view(), name="public-booking-confirm"),
    path("cu/stores/", views.CustomerStoresView.as_view(), name="cu-stores"),
    path("cu/login/", views.customer_login, name="cu-login"),
    path("cu/signup/", views.customer_signup, name="cu-signup"),
    path("cu/activate/preview/", views.customer_activation_preview, name="cu-activate-preview"),
    path("cu/activate/", views.customer_activate, name="cu-activate"),
    path("cu/mypage/", views.CustomerMypageView.as_view(), name="cu-mypage"),
    path("cu/available-slots/", views.CustomerAvailableSlotsView.as_view(), name="cu-available-slots"),
    path("cu/booking/options/", views.CustomerBookingOptionsView.as_view(), name="cu-booking-options"),
    path("cu/bookings/", views.CustomerBookingCreateView.as_view(), name="cu-bookings"),
    path("cu/reservations/<int:pk>/", views.CustomerReservationDetailView.as_view(), name="cu-reservation-detail"),

    # operator
    path("op/orders/<int:pk>/cast-ack/", views.OpOrderCastAckView.as_view(), name="op-order-cast-ack"),
    path("op/orders/<int:pk>/sms-logs/", views.OrderSmsLogsView.as_view(), name="op-order-sms-logs"),
    path("op/customers/<int:pk>/invitation/", views.CustomerInvitationStatusView.as_view(), name="op-customer-invitation"),
    path("op/shifts/weekly/", views.WeeklyShiftView.as_view(), name="op-shifts-weekly"),
    path("op/schedule-cast-order/", views.ScheduleCastOrderView.as_view(), name="op-schedule-cast-order"),
    path("op/sms-templates/", views.SmsTemplateSettingsView.as_view(), name="op-sms-templates"),
    path(
        "op/public-booking-settings/",
        views.StorePublicBookingSettingsView.as_view(),
        name="op-public-booking-settings",
    ),
    path("op/schedule/", views.ScheduleView.as_view(), name="op-schedule"),
    path("op/room-schedule/", views.RoomScheduleView.as_view(), name="op-room-schedule"),
    path("op/csv-import/", views.CsvImportView.as_view(), name="csv-import"),
    path("op/csv-import/template/", views.CsvImportTemplateView.as_view(), name="csv-import-template"),
    path("op/daily-settlement/", views.DailySettlementView.as_view(), name="daily-settlement"),
    path("op/daily-settlement/lock/", views.DailySettlementLockView.as_view(), name="daily-settlement-lock"),
    path("op/daily-settlement/unlock/", views.DailySettlementUnlockView.as_view(), name="daily-settlement-unlock"),
    path("op/daily-settlement/export/", views.DailySettlementExportView.as_view(), name="daily-settlement-export"),
    path("op/sales-summary/", views.SalesSummaryView.as_view(), name="sales-summary"),
    path("op/sales-export.csv", views.SalesExportView.as_view(), name="sales-export"),
    path("op/sales-dashboard/", views.SalesDashboardView.as_view(), name="sales-dashboard"),
    path("op/sales-dashboard-export.csv", views.SalesDashboardExportView.as_view(), name="sales-dashboard-export"),
    path("op/customers-export.csv", views.CustomerExportView.as_view(), name="customers-export"),
    path("op/line-alerts/", views.LineAlertsView.as_view(), name="line-alerts"),
    path("op/shift-end-alerts/", views.ShiftEndAlertsView.as_view(), name="shift-end-alerts"),
    path("op/shift-confirm-alerts/", views.ShiftConfirmAlertsView.as_view(), name="shift-confirm-alerts"),
    path(
        "op/shift-confirm-alerts/<int:shift_id>/mark_notification_test/",
        views.ShiftConfirmNotificationTestView.as_view(),
        name="shift-confirm-notification-test",
    ),
    path("op/line-settings/", views.StoreLineSettingsView.as_view(), name="store-line-settings"),
    path("op/payment-fee-settings/", views.StorePaymentFeeSettingsView.as_view(), name="store-payment-fee-settings"),
    path(
        "op/sip-provisioning/settings/",
        views.StoreSipProvisioningSettingsView.as_view(),
        name="store-sip-provisioning-settings",
    ),
    path(
        "op/sip-reception-devices/",
        views.SipReceptionDeviceListCreateView.as_view(),
        name="sip-reception-device-list-create",
    ),
    path(
        "op/sip-reception-devices/<int:device_id>/provision/",
        views.SipReceptionDeviceProvisionView.as_view(),
        name="sip-reception-device-provision",
    ),
    path(
        "op/sip-reception-devices/<int:device_id>/deactivate/",
        views.SipReceptionDeviceDeactivateView.as_view(),
        name="sip-reception-device-deactivate",
    ),
    path("op/", include(op_sr_router.urls)),

    # Groundwire設定案内（短時間・使い切りURL）
    path(
        "provisioning/groundwire/<str:token>/",
        views.GroundwireProvisioningView.as_view(),
        name="groundwire-provisioning",
    ),

    # Twilio webhook
    path(
        "webhook/twilio/regulatory-status/",
        views.twilio_regulatory_status_webhook,
        name="twilio-regulatory-status-webhook",
    ),
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
