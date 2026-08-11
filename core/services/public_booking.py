import re
import secrets
from datetime import date as date_type, timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.models import (
    Cast,
    Course,
    Customer,
    Option,
    Order,
    PublicBookingVerification,
    ShiftAssignment,
    SmsLog,
    Store,
)
from core.serializers import OrderCreateSerializer
from core.services.notify import notify_cast_order, notify_order_confirmed, send_sms
from core.services.order_availability import build_available_order_slots
from core.utils.phone import normalize_phone


VERIFICATION_LIFETIME = timedelta(minutes=10)
VERIFICATION_MAX_ATTEMPTS = 5
VERIFICATION_REQUEST_LIMIT = 3
VERIFICATION_REQUEST_WINDOW = timedelta(minutes=10)
INVALID_VERIFICATION_MESSAGE = "認証コードが正しくないか、有効期限が切れています。"


class PublicBookingError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def generate_public_booking_code():
    return f"{secrets.randbelow(1_000_000):06d}"


def serialize_public_booking_options(store, business_date=None):
    cast_queryset = Cast.objects.filter(store=store).order_by("name")
    shifts_by_cast = {}
    if business_date is not None:
        shifts = ShiftAssignment.objects.filter(
            store=store,
            date=business_date,
            is_absent=False,
        ).select_related("room").order_by("start_time", "id")
        for shift in shifts:
            shifts_by_cast.setdefault(shift.cast_id, []).append(shift)
        cast_queryset = cast_queryset.filter(pk__in=shifts_by_cast)

    casts = []
    for cast in cast_queryset:
        shift_summaries = []
        for shift in shifts_by_cast.get(cast.id, []):
            shift_summaries.append({
                "room_name": shift.room.name,
                "area_name": shift.room.area_name or "その他",
                "start": shift.start_time.strftime("%H:%M"),
                "end": (
                    f"{shift.end_time.hour + (24 * shift.end_day_offset):02d}"
                    f":{shift.end_time.minute:02d}"
                ),
            })
        casts.append({
            "id": cast.id,
            "name": cast.name,
            "avatar_url": cast.avatar_url,
            "introduction": cast.introduction,
            "shift_summaries": shift_summaries,
            "area_names": sorted({item["area_name"] for item in shift_summaries}),
        })
    courses = []
    for course in Course.objects.filter(store=store).prefetch_related("target_casts").order_by("id"):
        courses.append({
            "id": course.id,
            "name": course.name,
            "duration": course.duration,
            "price": course.price,
            "target_cast_ids": list(course.target_casts.values_list("id", flat=True)),
        })
    options = [
        {"id": option.id, "name": option.name, "price": option.price}
        for option in Option.objects.filter(store=store).order_by("id")
    ]
    return {
        "store": {"id": store.id, "name": store.name},
        "casts": casts,
        "courses": courses,
        "options": options,
    }


def get_public_booking_slots(store, cast_id, course_id, business_date, now=None):
    cast = Cast.objects.filter(store=store, pk=cast_id).first()
    course = Course.objects.filter(store=store, pk=course_id).first()
    if cast is None or course is None:
        return []
    if course.target_casts.exists() and not course.target_casts.filter(pk=cast.pk).exists():
        return []
    return build_available_order_slots(
        store,
        cast,
        business_date,
        duration_minutes=course.duration,
        not_before=now or timezone.now(),
    )


def _required_store(store_id):
    try:
        store_id = int(store_id)
    except (TypeError, ValueError):
        raise PublicBookingError("店舗を選択してください。")
    store = Store.objects.filter(pk=store_id).first()
    if store is None:
        raise PublicBookingError("店舗を選択してください。")
    return store


def _normalize_booking_phone(value):
    phone = normalize_phone(str(value or "").strip())
    if not re.fullmatch(r"0\d{9,10}", phone):
        raise PublicBookingError("有効な電話番号を入力してください。")
    return phone


def _clean_display_name(value):
    display_name = str(value or "").strip()
    if not display_name:
        raise PublicBookingError("お名前を入力してください。")
    if len(display_name) > 50:
        raise PublicBookingError("お名前は50文字以内で入力してください。")
    return display_name


def _clean_booking_selection(data, store, now=None, lock_cast=False):
    try:
        cast_id = int(data.get("cast"))
        course_id = int(data.get("course"))
        business_date = date_type.fromisoformat(str(data.get("date") or ""))
    except (TypeError, ValueError):
        raise PublicBookingError("キャスト、コース、予約日を選択してください。")

    cast_queryset = Cast.objects.select_for_update() if lock_cast else Cast.objects
    cast = cast_queryset.filter(store=store, pk=cast_id).first()
    course = Course.objects.filter(store=store, pk=course_id).first()
    if cast is None or course is None:
        raise PublicBookingError("選択された予約内容を確認できません。")
    if course.target_casts.exists() and not course.target_casts.filter(pk=cast.pk).exists():
        raise PublicBookingError("このコースは選択したキャストでは予約できません。")

    start = parse_datetime(str(data.get("start") or ""))
    if start is None or start.utcoffset() is None:
        raise PublicBookingError("予約時刻を選択してください。")

    available_slots = get_public_booking_slots(
        store,
        cast.id,
        course.id,
        business_date,
        now=now or timezone.now(),
    )
    matching_slot = next(
        (
            slot for slot in available_slots
            if parse_datetime(slot["start_at"]) == start
        ),
        None,
    )
    if matching_slot is None:
        raise PublicBookingError(
            "選択した時間は埋まったか、現在予約できません。空き時間を選び直してください。",
            status_code=409,
        )

    raw_option_ids = data.get("options") or []
    if not isinstance(raw_option_ids, list):
        raise PublicBookingError("オプションの指定が正しくありません。")
    try:
        option_ids = sorted({int(option_id) for option_id in raw_option_ids})
    except (TypeError, ValueError):
        raise PublicBookingError("オプションの指定が正しくありません。")
    options = list(Option.objects.filter(store=store, pk__in=option_ids).order_by("id"))
    if len(options) != len(option_ids):
        raise PublicBookingError("選択されたオプションを確認できません。")

    memo = str(data.get("memo") or "").strip()
    if len(memo) > 1000:
        raise PublicBookingError("備考は1000文字以内で入力してください。")

    return {
        "cast": cast,
        "course": course,
        "business_date": business_date,
        "start": start,
        "options": options,
        "memo": memo,
        "slot": matching_slot,
    }


def request_public_booking_verification(data):
    store = _required_store(data.get("store"))
    phone = _normalize_booking_phone(data.get("phone"))
    display_name = _clean_display_name(data.get("display_name"))
    selection = _clean_booking_selection(data, store)
    now = timezone.now()

    recent_count = PublicBookingVerification.objects.filter(
        phone=phone,
        created_at__gte=now - VERIFICATION_REQUEST_WINDOW,
    ).count()
    if recent_count >= VERIFICATION_REQUEST_LIMIT:
        raise PublicBookingError(
            "認証コードの送信回数が上限に達しました。しばらく待ってからお試しください。",
            status_code=429,
        )

    code = generate_public_booking_code()
    challenge = PublicBookingVerification.objects.create(
        store=store,
        phone=phone,
        display_name=display_name,
        booking_payload={
            "cast": selection["cast"].id,
            "course": selection["course"].id,
            "date": selection["business_date"].isoformat(),
            "start": selection["start"].isoformat(),
            "options": [option.id for option in selection["options"]],
            "memo": selection["memo"],
        },
        code_hash=make_password(code),
        expires_at=now + VERIFICATION_LIFETIME,
    )
    sms_log = send_sms(
        to_phone=phone,
        body=(
            f"【Roomink】Web予約の認証コードは {code} です。\n"
            "10分以内に予約画面へ入力してください。"
        ),
        template_type=SmsLog.TemplateType.OTHER,
        log_body="【Roomink】Web予約認証コード: [認証コード]",
    )
    sms_log.store = store
    sms_log.save(update_fields=["store"])
    challenge.sms_log = sms_log
    challenge.save(update_fields=["sms_log"])

    if sms_log.status not in (SmsLog.Status.SENT, SmsLog.Status.DUMMY):
        challenge.delete()
        raise PublicBookingError(
            "現在SMS認証を利用できません。時間をおいて再度お試しください。",
            status_code=503,
        )

    return {
        "verification_id": str(challenge.id),
        "masked_phone": f"***{phone[-4:]}",
        "expires_in_seconds": int(VERIFICATION_LIFETIME.total_seconds()),
    }


def _find_or_create_verified_customer(challenge):
    candidates = list(
        Customer.objects.select_for_update()
        .filter(store=challenge.store, phone__endswith=challenge.phone[-4:])
    )
    matching = [
        customer for customer in candidates
        if normalize_phone(customer.phone) == challenge.phone
    ]
    if len(matching) > 1:
        raise PublicBookingError("予約を受け付けられません。店舗へお問い合わせください。")
    if matching:
        customer = matching[0]
        if customer.flag == Customer.Flag.BAN:
            raise PublicBookingError("予約を受け付けられません。店舗へお問い合わせください。")
        if not customer.display_name:
            customer.display_name = challenge.display_name
            customer.save(update_fields=["display_name"])
        return customer
    return Customer.objects.create(
        store=challenge.store,
        phone=challenge.phone,
        display_name=challenge.display_name,
    )


def confirm_public_booking(verification_id, code):
    code = str(code or "").strip()
    if not re.fullmatch(r"\d{6}", code):
        raise PublicBookingError(INVALID_VERIFICATION_MESSAGE)

    now = timezone.now()
    wrong_code = False
    with transaction.atomic():
        try:
            challenge = (
                PublicBookingVerification.objects
                .select_for_update()
                .select_related("store")
                .get(pk=verification_id)
            )
        except (
            PublicBookingVerification.DoesNotExist,
            DjangoValidationError,
            TypeError,
            ValueError,
        ):
            raise PublicBookingError(INVALID_VERIFICATION_MESSAGE)

        if (
            challenge.consumed_at is not None
            or challenge.expires_at <= now
            or challenge.failed_attempts >= VERIFICATION_MAX_ATTEMPTS
        ):
            raise PublicBookingError(INVALID_VERIFICATION_MESSAGE)

        if not check_password(code, challenge.code_hash):
            challenge.failed_attempts += 1
            challenge.save(update_fields=["failed_attempts"])
            wrong_code = True
        else:
            challenge.store = Store.objects.select_for_update().get(
                pk=challenge.store_id,
            )
            selection = _clean_booking_selection(
                challenge.booking_payload,
                challenge.store,
                now=now,
                lock_cast=True,
            )
            customer = _find_or_create_verified_customer(challenge)
            account_setup_required = customer.user_id is None
            serializer = OrderCreateSerializer(data={
                "customer": customer.id,
                "cast": selection["cast"].id,
                "course": selection["course"].id,
                "start": selection["start"].isoformat(),
                "options": [option.id for option in selection["options"]],
                "memo": selection["memo"],
                "service_recipient_name": "",
                "payment_method": Order.PaymentMethod.UNSET,
            })
            if not serializer.is_valid():
                raise PublicBookingError(
                    "選択した時間は埋まったか、現在予約できません。空き時間を選び直してください。",
                    status_code=409,
                )
            order = serializer.save()
            order.status = Order.Status.CONFIRMED
            order.save(update_fields=["status", "updated_at"])
            challenge.consumed_at = now
            challenge.save(update_fields=["consumed_at"])

    if wrong_code:
        raise PublicBookingError(INVALID_VERIFICATION_MESSAGE)

    customer_sms = notify_order_confirmed(order)
    notify_cast_order(order)
    return {
        "id": order.id,
        "status": order.status,
        "store_name": order.store.name,
        "cast_name": order.cast.name,
        "course_name": order.course_name,
        "start": order.start.isoformat(),
        "end": order.end.isoformat(),
        "total_price": order.total_price,
        "room_name": order.room.name if order.room else "",
        "room_address": order.room.address if order.room else "",
        "account_setup_required": account_setup_required,
        "sms_status": customer_sms.status,
    }
