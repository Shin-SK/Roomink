from datetime import date, timedelta

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ShiftAssignment, Store, UserProfile
from .permissions import IsManager
from .services.attendance import can_clock_in, save_attendance, serialize_attendance
from .services.business_datetime import business_date_for_datetime, build_business_interval
from .store_access import get_request_profile, get_user_store
from .views import document_object_api_view


def require_cast(request):
    profile = get_request_profile(request)
    cast = getattr(request.user, "cast_profile", None)
    if not cast or not profile or profile.role != UserProfile.Role.CAST or profile.store_id != cast.store_id:
        raise PermissionDenied("所属店舗のセラピスト本人だけ利用できます")
    return cast


@document_object_api_view
@method_decorator(transaction.atomic, name="dispatch")
class CastAttendanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cast = require_cast(request)
        today = business_date_for_datetime(timezone.now(), cast.store.timezone, cast.store.business_day_boundary_hour)
        shifts = ShiftAssignment.objects.filter(cast=cast, store=cast.store).filter(
            Q(date__range=(today - timedelta(days=1), today)) |
            Q(clocked_in_at__isnull=False, clocked_out_at__isnull=True)
        ).select_related("store", "cast").order_by("date", "start_day_offset", "start_time", "id")
        return Response({"current_business_date": today.isoformat(), "shifts": [serialize_attendance(shift) for shift in shifts]})

    def post(self, request):
        cast = require_cast(request)
        if set(request.data) - {"shift_id", "action"}:
            raise ValidationError("指定できない項目が含まれています")
        shift_id = serializers.IntegerField(min_value=1).run_validation(request.data.get("shift_id"))
        action = serializers.ChoiceField(choices=["clock_in", "clock_out"]).run_validation(request.data.get("action"))
        Store.objects.select_for_update().get(pk=cast.store_id)
        shift = get_object_or_404(ShiftAssignment.objects.select_for_update().select_related("store", "cast"),
                                  pk=shift_id, cast=cast, store=cast.store)
        now = timezone.now()
        if action == "clock_in":
            if shift.clocked_in_at:
                return Response(serialize_attendance(shift))
            start, end = build_business_interval(
                shift.date, shift.start_time, shift.end_time, start_day_offset=shift.start_day_offset,
                end_day_offset=shift.end_day_offset, timezone_name=cast.store.timezone,
            )
            if not can_clock_in(shift, now, start, end):
                raise ValidationError("本日の勤務だけ出勤を打刻できます。打刻忘れは店舗へ訂正を依頼してください")
            save_attendance(shift, actor=request.user, action=action, clocked_in_at=now, clocked_out_at=None)
        else:
            if not shift.clocked_in_at:
                raise ValidationError("出勤記録がありません。店舗へ確認してください")
            save_attendance(shift, actor=request.user, action=action,
                            clocked_in_at=shift.clocked_in_at, clocked_out_at=shift.clocked_out_at or now)
        return Response(serialize_attendance(shift))


class AttendanceSnapshotSerializer(serializers.Serializer):
    clocked_in_at = serializers.DateTimeField(allow_null=True)
    clocked_out_at = serializers.DateTimeField(allow_null=True)


class AttendanceCorrectionSerializer(AttendanceSnapshotSerializer):
    shift_id = serializers.IntegerField(min_value=1)
    clocked_in_at = serializers.DateTimeField(allow_null=True)
    clocked_out_at = serializers.DateTimeField(allow_null=True)
    expected = AttendanceSnapshotSerializer()
    reason = serializers.CharField(max_length=500, allow_blank=False)


@document_object_api_view
@method_decorator(transaction.atomic, name="dispatch")
class ManagerAttendanceView(APIView):
    permission_classes = [IsAuthenticated, IsManager]

    def get(self, request):
        store = get_user_store(request)
        try:
            day = date.fromisoformat(request.query_params.get("date", ""))
        except (TypeError, ValueError):
            raise ValidationError("対象日をYYYY-MM-DDで指定してください")
        shifts = ShiftAssignment.objects.filter(store=store).filter(
            Q(date=day) | Q(date__lt=day, clocked_in_at__isnull=False, clocked_out_at__isnull=True)
        ).select_related("cast", "store").prefetch_related("attendance_events__recorded_by").order_by("date", "cast__name", "id")
        return Response({"shifts": [serialize_attendance(shift, include_history=True) for shift in shifts]})

    def post(self, request):
        serializer = AttendanceCorrectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        store = get_user_store(request)
        Store.objects.select_for_update().get(pk=store.pk)
        shift = get_object_or_404(ShiftAssignment.objects.select_for_update().select_related("cast", "store"),
                                  pk=data["shift_id"], store=store)
        if data["expected"] != {key: getattr(shift, key) for key in ("clocked_in_at", "clocked_out_at")}:
            return Response({"detail": "打刻が更新されています。最新内容を読み直してください"}, status=409)
        if any(data[key] and data[key] > timezone.now() for key in ("clocked_in_at", "clocked_out_at")):
            raise ValidationError("未来の打刻時刻は登録できません")
        save_attendance(shift, actor=request.user, action="correction", reason=data["reason"],
                        clocked_in_at=data["clocked_in_at"], clocked_out_at=data["clocked_out_at"])
        return Response(serialize_attendance(shift, include_history=True))
