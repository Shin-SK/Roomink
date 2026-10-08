"""Roomink account security policy shared by every password-setting path."""

from ipaddress import ip_address

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.http import JsonResponse

from core.models import Customer, UserProfile


ROLE_MIN_LENGTH = {
    "superuser": 20,
    UserProfile.Role.MANAGER: 10,
    UserProfile.Role.STAFF: 10,
    UserProfile.Role.CAST: 8,
    "customer": 8,
}

ROLE_SESSION_AGE = {
    "superuser": 12 * 60 * 60,
    UserProfile.Role.MANAGER: 14 * 24 * 60 * 60,
    UserProfile.Role.STAFF: 14 * 24 * 60 * 60,
    UserProfile.Role.CAST: 90 * 24 * 60 * 60,
    "customer": 90 * 24 * 60 * 60,
}


def security_role_for_user(user):
    if user is not None and user.is_superuser:
        return "superuser"
    profile = getattr(user, "profile", None) if user is not None else None
    if profile is not None:
        return profile.role
    if user is not None and user.pk and Customer.objects.filter(user=user).exists():
        return "customer"
    return UserProfile.Role.CAST


def minimum_password_length(*, user=None, role=None):
    effective_role = role or security_role_for_user(user)
    return ROLE_MIN_LENGTH.get(effective_role, 8)


def validate_password_for_role(password, *, user=None, role=None):
    """Run Django's mature validators plus Roomink's role-based length floor."""
    errors = []
    try:
        validate_password(password, user=user)
    except ValidationError as exc:
        errors.extend(exc.messages)

    minimum = minimum_password_length(user=user, role=role)
    if len(password or "") < minimum:
        errors.append(f"このアカウントのパスワードは{minimum}文字以上にしてください。")

    if errors:
        raise ValidationError(list(dict.fromkeys(errors)))


def password_policy_for_user(user):
    role = security_role_for_user(user)
    return {
        "role": role,
        "min_length": minimum_password_length(role=role),
        "requires_uppercase": False,
        "requires_symbol": False,
        "mfa_required": False,
    }


def apply_session_expiry(request, user):
    role = security_role_for_user(user)
    request.session.set_expiry(ROLE_SESSION_AGE.get(role, 14 * 24 * 60 * 60))


def axes_client_ip_address(request):
    """Resolve the stable client address from Heroku's forwarding chain.

    Heroku appends the address it observed to the right of any caller-supplied
    X-Forwarded-For values. Dynos are only reachable through the router, so the
    validated right-most entry is the value suitable for login lockout keys.
    """
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    candidate = forwarded_for.rsplit(",", 1)[-1].strip() if forwarded_for else ""
    try:
        return str(ip_address(candidate))
    except ValueError:
        remote_addr = (request.META.get("REMOTE_ADDR") or "").strip()
        try:
            return str(ip_address(remote_addr))
        except ValueError:
            return None


def axes_lockout_response(request, response, credentials, *args, **kwargs):
    return JsonResponse(
        {"detail": "ログイン試行が多すぎます。15分後にもう一度お試しください。"},
        status=429,
    )
