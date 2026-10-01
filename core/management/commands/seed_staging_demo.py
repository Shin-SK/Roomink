import os
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import (
    Cast,
    Course,
    Customer,
    Option,
    Order,
    Room,
    ShiftAssignment,
    Store,
    UserProfile,
)


STORE_SLUG = "flagship-staging"
MANAGER_USERNAME = "staging_manager"
CAST_USERNAME = "sample-cast"


class Command(BaseCommand):
    help = "ステージング専用の匿名化済みデモ店舗を作成します。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="既存のステージングデモ店舗を削除して作り直します。",
        )

    def handle(self, *args, **options):
        if os.getenv("DJANGO_ENV", "").strip().lower() != "staging":
            raise CommandError("このコマンドはDJANGO_ENV=stagingでのみ実行できます。")
        if os.getenv("SMS_DUMMY_MODE", "0") != "1":
            raise CommandError("SMS_DUMMY_MODE=1が必要です。")

        manager_password = os.getenv("STAGING_MANAGER_PASSWORD", "")
        cast_password = os.getenv("STAGING_CAST_PASSWORD", "")
        if not manager_password or not cast_password:
            raise CommandError(
                "STAGING_MANAGER_PASSWORDとSTAGING_CAST_PASSWORDを"
                "環境変数へ設定してください。"
            )

        with transaction.atomic():
            existing = Store.objects.filter(slug=STORE_SLUG).first()
            if existing and not options["reset"]:
                raise CommandError(
                    "ステージングデモ店舗は作成済みです。"
                    "作り直す場合は--resetを付けてください。"
                )
            if existing:
                user_ids = list(existing.user_profiles.values_list("user_id", flat=True))
                existing.delete()
                get_user_model().objects.filter(pk__in=user_ids).delete()

            User = get_user_model()
            User.objects.filter(username__in=[MANAGER_USERNAME, CAST_USERNAME]).delete()

            store = Store.objects.create(
                name="フラッグシップ（ステージング）",
                slug=STORE_SLUG,
                timezone="Asia/Tokyo",
                sms_billing_exempt=True,
                public_booking_notice=(
                    "これはRoominkの検証環境です。"
                    "実際の予約・連絡には使用されません。"
                ),
                public_booking_notification_email="",
                guest_contact_phone="",
                line_is_enabled=False,
                sip_username="",
                sip_password="",
                sip_domain="",
            )

            rooms = [
                Room.objects.create(
                    store=store,
                    name=name,
                    area_name="高田馬場",
                    address="東京都新宿区 テスト住所",
                    sort_order=index,
                )
                for index, name in enumerate(
                    ["テストルームA", "テストルームB", "テストルームC"],
                    start=1,
                )
            ]
            casts = [
                Cast.objects.create(store=store, name=name, interval_minutes=15)
                for name in ["テスト花", "テスト美紀", "テスト萌"]
            ]
            courses = [
                Course.objects.create(store=store, name=name, duration=duration, price=price)
                for name, duration, price in [
                    ("スタンダード90分", 90, 17000),
                    ("スタンダード120分", 120, 22000),
                    ("スペシャル70分", 70, 19000),
                    ("スペシャル100分", 100, 24000),
                ]
            ]
            options_seed = [
                Option.objects.create(store=store, name=name, price=price)
                for name, price in [
                    ("衣装チェンジ", 4000),
                    ("ディープリンパ", 0),
                    ("テストオプション", 2000),
                ]
            ]

            local_today = timezone.now().astimezone(ZoneInfo(store.timezone)).date()
            for day_offset in range(7):
                business_date = local_today + timedelta(days=day_offset)
                for index, cast in enumerate(casts):
                    end_hour = 22 + index
                    ShiftAssignment.objects.create(
                        store=store,
                        date=business_date,
                        cast=cast,
                        room=rooms[index],
                        start_time=time(11 + index, 0),
                        end_time=time(end_hour % 24, 0),
                        end_day_offset=1 if end_hour >= 24 else 0,
                        display_order=index + 1,
                    )

            customers = [
                Customer.objects.create(
                    store=store,
                    phone=f"0900000000{index}",
                    display_name=f"テスト顧客{index}",
                    memo="ステージング専用の架空データ",
                )
                for index in range(1, 4)
            ]

            tokyo = ZoneInfo(store.timezone)
            start_times = [
                datetime.combine(local_today, time(13, 0), tzinfo=tokyo),
                datetime.combine(local_today, time(15, 30), tzinfo=tokyo),
                datetime.combine(local_today, time(18, 0), tzinfo=tokyo),
            ]
            statuses = [
                Order.Status.CONFIRMED,
                Order.Status.REQUESTED,
                Order.Status.DONE,
            ]
            timeline_statuses = [
                Order.TimelineStatus.SMS_CONFIRMED,
                Order.TimelineStatus.AUTO,
                Order.TimelineStatus.CARD_PAID,
            ]
            for index, start in enumerate(start_times):
                course = courses[index]
                order = Order.objects.create(
                    store=store,
                    cast=casts[index],
                    room=rooms[index],
                    customer=customers[index],
                    course=course,
                    course_name=course.name,
                    course_price=course.price,
                    total_price=course.price,
                    start=start,
                    end=start + timedelta(minutes=course.duration),
                    status=statuses[index],
                    timeline_status=timeline_statuses[index],
                    payment_method=Order.PaymentMethod.CASH,
                    memo="ステージング表示確認用",
                )
                if index == 0:
                    order.options.add(options_seed[0])

            manager = User.objects.create_user(
                username=MANAGER_USERNAME,
                password=manager_password,
                email="",
            )
            UserProfile.objects.create(
                user=manager,
                store=store,
                role=UserProfile.Role.MANAGER,
            )

            cast_user = User.objects.create_user(
                username=CAST_USERNAME,
                password=cast_password,
                email="",
            )
            UserProfile.objects.create(
                user=cast_user,
                store=store,
                role=UserProfile.Role.CAST,
            )
            casts[0].user = cast_user
            casts[0].save(update_fields=["user"])

        self.stdout.write(
            self.style.SUCCESS("匿名化済みステージングデータを作成しました。")
        )
        self.stdout.write(f"store={store.slug}")
        self.stdout.write(f"manager={MANAGER_USERNAME}")
        self.stdout.write(f"cast={CAST_USERNAME}")
        self.stdout.write("実在顧客・本番電話番号・本番通知先は含まれていません。")
