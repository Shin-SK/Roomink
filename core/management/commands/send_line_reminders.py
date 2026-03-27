"""
LINE 出勤リマインド通知を送信する management command。
5分間隔の cron / Heroku Scheduler で実行する想定。

Usage:
    python3 manage.py send_line_reminders
"""
import logging
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import LineNotificationLog, ShiftAssignment, Store
from core.services.line_notify import send_line_push

logger = logging.getLogger(__name__)

# 判定窓の幅（分）。cron 間隔と合わせる。
WINDOW_MINUTES = 10

# 朝通知の送信時刻
MORNING_HOUR = 8
MORNING_MINUTE = 0


class Command(BaseCommand):
    help = "LINE 出勤リマインド通知を送信"

    def handle(self, *args, **options):
        stores = Store.objects.all()
        total_sent = 0

        for store in stores:
            try:
                import zoneinfo
                tz = zoneinfo.ZoneInfo(store.timezone)
            except Exception:
                import pytz
                tz = pytz.timezone(store.timezone)

            now = timezone.now().astimezone(tz)
            today = now.date()

            shifts = (
                ShiftAssignment.objects
                .filter(store=store, date=today)
                .select_related("cast")
            )

            for shift in shifts:
                shift_start_dt = datetime.combine(today, shift.start_time, tzinfo=tz)

                # 朝通知: MORNING_HOUR:MORNING_MINUTE の窓内
                morning_target = now.replace(hour=MORNING_HOUR, minute=MORNING_MINUTE, second=0, microsecond=0)
                if morning_target <= now < morning_target + timedelta(minutes=WINDOW_MINUTES):
                    if self._should_send(shift, LineNotificationLog.NotificationType.MORNING):
                        msg = f"【Roomink】{shift.cast.name}さん、本日 {shift.start_time.strftime('%H:%M')} から出勤です。よろしくお願いします。"
                        send_line_push(shift.cast, msg, shift, LineNotificationLog.NotificationType.MORNING)
                        total_sent += 1

                # 2時間前
                two_h_before = shift_start_dt - timedelta(hours=2)
                if two_h_before <= now < two_h_before + timedelta(minutes=WINDOW_MINUTES):
                    if self._should_send(shift, LineNotificationLog.NotificationType.TWO_HOURS_BEFORE):
                        msg = f"【Roomink】{shift.cast.name}さん、出勤2時間前です（{shift.start_time.strftime('%H:%M')}〜）。"
                        send_line_push(shift.cast, msg, shift, LineNotificationLog.NotificationType.TWO_HOURS_BEFORE)
                        total_sent += 1

                # 15分前
                fifteen_min_before = shift_start_dt - timedelta(minutes=15)
                if fifteen_min_before <= now < fifteen_min_before + timedelta(minutes=WINDOW_MINUTES):
                    if self._should_send(shift, LineNotificationLog.NotificationType.FIFTEEN_MIN_BEFORE):
                        msg = f"【Roomink】{shift.cast.name}さん、出勤15分前です（{shift.start_time.strftime('%H:%M')}〜）。準備をお願いします。"
                        send_line_push(shift.cast, msg, shift, LineNotificationLog.NotificationType.FIFTEEN_MIN_BEFORE)
                        total_sent += 1

        self.stdout.write(f"送信完了: {total_sent}件")

    def _should_send(self, shift, notification_type):
        """既に送信済み（SENT/SKIPPED）なら False"""
        return not LineNotificationLog.objects.filter(
            shift_assignment=shift,
            notification_type=notification_type,
            status__in=[
                LineNotificationLog.Status.SENT,
                LineNotificationLog.Status.SKIPPED,
            ],
        ).exists()
