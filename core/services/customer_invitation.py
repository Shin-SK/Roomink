import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import Customer, CustomerAccountInvitation, SmsLog
from core.utils.phone import normalize_phone


INVITATION_LIFETIME = timedelta(hours=72)
INVALID_INVITATION_MESSAGE = "この案内は利用できません。店舗へお問い合わせください。"


def hash_invitation_token(raw_token):
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def issue_customer_invitation(customer, order=None, created_by=None, force=False):
    """平文トークンは呼び出し元にだけ返し、DBにはSHA-256ハッシュだけを保存する。"""
    if not settings.FRONTEND_URL:
        return None, None

    now = timezone.now()
    with transaction.atomic():
        locked_customer = Customer.objects.select_for_update().get(pk=customer.pk)
        if locked_customer.user_id:
            return None, None

        active = (
            CustomerAccountInvitation.objects
            .filter(
                customer=locked_customer,
                used_at__isnull=True,
                invalidated_at__isnull=True,
                expires_at__gt=now,
            )
            .order_by("-created_at")
            .first()
        )
        if active and not force:
            return active, None

        if force:
            CustomerAccountInvitation.objects.filter(
                customer=locked_customer,
                used_at__isnull=True,
                invalidated_at__isnull=True,
            ).update(invalidated_at=now)

        raw_token = secrets.token_urlsafe(32)
        invitation = CustomerAccountInvitation.objects.create(
            customer=locked_customer,
            order=order,
            token_hash=hash_invitation_token(raw_token),
            expires_at=now + INVITATION_LIFETIME,
            created_by=created_by if (created_by and created_by.is_authenticated) else None,
        )
    return invitation, raw_token


def get_valid_invitation(raw_token, for_update=False):
    if not raw_token:
        return None
    if for_update:
        # PostgreSQLではnullableなorderへの外部結合をFOR UPDATEできないため、
        # 更新時は招待行と必須FKのcustomerだけを取得する。
        queryset = CustomerAccountInvitation.objects.select_related(
            "customer__store",
        ).select_for_update()
    else:
        queryset = CustomerAccountInvitation.objects.select_related(
            "customer__store",
            "order",
        )
    invitation = queryset.filter(token_hash=hash_invitation_token(raw_token)).first()
    now = timezone.now()
    if (
        invitation is None
        or invitation.used_at is not None
        or invitation.invalidated_at is not None
        or invitation.expires_at <= now
        or invitation.customer.user_id is not None
    ):
        return None
    return invitation


def activate_customer_invitation(request, raw_token, password, password_confirm):
    if password != password_confirm:
        raise ValidationError("パスワードが一致しません。")

    User = get_user_model()
    with transaction.atomic():
        invitation = get_valid_invitation(raw_token, for_update=True)
        if invitation is None:
            raise ValidationError(INVALID_INVITATION_MESSAGE)

        customer = Customer.objects.select_for_update().get(pk=invitation.customer_id)
        phone = normalize_phone(customer.phone)
        if not phone:
            raise ValidationError(INVALID_INVITATION_MESSAGE)

        matching_customers = Customer.objects.filter(
            user__isnull=False,
            phone__endswith=phone[-4:],
        ).select_related("user")
        matching_users = {
            profile.user_id: profile.user
            for profile in matching_customers
            if normalize_phone(profile.phone) == phone
        }
        if len(matching_users) > 1:
            raise ValidationError(INVALID_INVITATION_MESSAGE)

        existing_user = next(iter(matching_users.values()), None)
        username_collision = User.objects.filter(username=phone).first()
        if existing_user is None and username_collision is None:
            pending_user = User(username=phone, first_name=customer.display_name or "")
            validate_password(password, user=pending_user)
            user = User.objects.create_user(
                username=phone,
                password=password,
                first_name=customer.display_name or "",
            )
        elif existing_user is not None:
            if not existing_user.check_password(password):
                raise ValidationError(INVALID_INVITATION_MESSAGE)
            user = existing_user
        else:
            raise ValidationError(INVALID_INVITATION_MESSAGE)

        customer.user = user
        customer.save(update_fields=["user"])
        invitation.used_at = timezone.now()
        invitation.save(update_fields=["used_at"])
        order_id = invitation.order_id
        store_slug = customer.store.slug

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    base_path = f"/s/{store_slug}/mypage"
    next_path = f"{base_path}/reservations/{order_id}" if order_id else base_path
    return user, next_path


def serialize_invitation_status(customer):
    invitation = (
        CustomerAccountInvitation.objects
        .filter(customer=customer)
        .select_related("sms_log")
        .order_by("-created_at")
        .first()
    )
    if customer.user_id:
        state = "ACCOUNT_CREATED"
    elif invitation is None:
        state = "NOT_ISSUED"
    elif invitation.used_at:
        state = "USED"
    elif invitation.invalidated_at:
        state = "INVALIDATED"
    elif invitation.expires_at <= timezone.now():
        state = "EXPIRED"
    else:
        state = "ACTIVE"

    sms_log = invitation.sms_log if invitation else (
        SmsLog.objects
        .filter(customer=customer, template_type=SmsLog.TemplateType.RESERVATION_CONFIRMATION)
        .order_by("-sent_at", "-id")
        .first()
    )
    return {
        "account_exists": customer.user_id is not None,
        "state": state,
        "created_at": invitation.created_at if invitation else None,
        "expires_at": invitation.expires_at if invitation else None,
        "used_at": invitation.used_at if invitation else None,
        "sms_status": sms_log.status if sms_log else None,
        "sms_status_label": sms_log.get_status_display() if sms_log else "",
    }
