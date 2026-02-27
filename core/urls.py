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

urlpatterns = [
    # auth
    path("auth/login/", views.auth_login, name="auth-login"),
    path("auth/logout/", views.auth_logout, name="auth-logout"),
    path("auth/me/", views.auth_me, name="auth-me"),

    # cast
    path("cast/today/", views.CastTodayView.as_view(), name="cast-today"),
    path("cast/orders/<int:pk>/ack/", views.CastAckView.as_view(), name="cast-ack"),

    # customer
    path("cu/stores/", views.CustomerStoresView.as_view(), name="cu-stores"),
    path("cu/signup/", views.customer_signup, name="cu-signup"),
    path("cu/mypage/", views.CustomerMypageView.as_view(), name="cu-mypage"),
    path("cu/booking/options/", views.CustomerBookingOptionsView.as_view(), name="cu-booking-options"),
    path("cu/bookings/", views.CustomerBookingCreateView.as_view(), name="cu-bookings"),

    # operator
    path("op/schedule/", views.ScheduleView.as_view(), name="op-schedule"),
    path("op/csv-import/", views.CsvImportView.as_view(), name="csv-import"),

    # router (orders, shifts, customers, casts, courses, options, rooms)
    path("", include(router.urls)),
]
