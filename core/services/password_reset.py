"""Email ownership is required before changing an existing account password."""
import hashlib
import logging
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from core.security import validate_password_for_role

logger = logging.getLogger(__name__)
RESET_SENT_MESSAGE = "登録済みのユーザー名であれば、再設定用メールを送信します。メールをご確認ください。"
INVALID_LINK_MESSAGE = "再設定リンクが無効か、有効期限が切れています。もう一度メールを送信してください。"


def reset_user(uid):
    try:
        pk = urlsafe_base64_decode(uid).decode()
        if not pk.isdecimal() or len(pk) > 20:
            return None
        return get_user_model().objects.filter(pk=pk, is_active=True).first()
    except (ValueError, TypeError, UnicodeDecodeError, OverflowError):
        return None


def valid_reset_user(uid, token):
    user = reset_user(uid)
    if user and user.email and user.has_usable_password() and default_token_generator.check_token(user, token):
        return user
    return None


def request_password_reset(username):
    # Do not reveal whether an account exists, has email, or is active.
    cooldown_key = 'password-reset:' + hashlib.sha256(username.casefold().encode()).hexdigest()
    if not cache.add(cooldown_key, True, timeout=60):
        return
    user = get_user_model().objects.filter(username=username, is_active=True).first()
    if not user or not user.email or not user.has_usable_password():
        return
    base = (settings.FRONTEND_URL or '').rstrip('/')
    parsed = urlsplit(base)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        logger.warning('Password reset email unavailable: frontend URL missing')
        return
    # Fragments are not sent in HTTP requests or Referrer headers.
    fragment = urlencode({'uid': urlsafe_base64_encode(force_bytes(user.pk)), 'token': default_token_generator.make_token(user)})
    url = f'{base}/password-reset#{fragment}'
    body = (
        'Roominkのパスワード再設定を受け付けました。\n\n'
        f'次のリンクから30分以内に新しいパスワードを設定してください。\n{url}\n\n'
        'リンクは一度だけ利用できます。変更後はほかの端末からログアウトされます。\n'
        'お心当たりがなければ、このメールを破棄してください。パスワードは変更されません。'
    )
    try:
        send_mail('【Roomink】パスワード再設定', body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
    except Exception:
        # SMTP exceptions can contain recipient addresses and message content.
        logger.warning('Password reset email delivery failed')


@transaction.atomic
def confirm_password_reset(uid, token, password):
    user = reset_user(uid)
    if user is None:
        return False
    # Check again while holding the row lock so a token cannot be used twice.
    user = get_user_model().objects.select_for_update().get(pk=user.pk)
    if not user.is_active or not user.email or not user.has_usable_password() or not default_token_generator.check_token(user, token):
        return False
    validate_password_for_role(password, user=user)
    user.set_password(password)
    user.save(update_fields=['password'])
    from axes.utils import reset
    reset(username=user.get_username())
    logger.info('Password reset completed: user_id=%s', user.pk)
    return True
