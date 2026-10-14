import hashlib
import re
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.models import Cast, LineRegistrationSession


REGISTRATION_TTL = timedelta(minutes=10)
MAX_CODE_ATTEMPTS = 5


def handle_cast_registration(text, source, channel_secret, store=None):
    """Return a reply only for explicit registration, never for ordinary inquiries."""
    user_id = source.get("userId", "")
    if source.get("type") != "user" or not user_id:
        return None
    scope = store.line_webhook_token if store else channel_secret
    identity = hashlib.sha256(f"{scope}:user:{user_id}".encode()).hexdigest()
    now = timezone.now()
    with transaction.atomic():
        # A linked account's ordinary conversations remain silent.
        if Cast.objects.filter(line_user_id=user_id).exists():
            LineRegistrationSession.objects.filter(identity_key=identity).delete()
            return "このLINEはすでにRoominkと連携済みです。" if text == "登録" else None
        if text == "登録":
            LineRegistrationSession.objects.filter(expires_at__lte=now).delete()
            LineRegistrationSession.objects.update_or_create(
                identity_key=identity,
                defaults={"expires_at": now + REGISTRATION_TTL, "failed_attempts": 0},
            )
            return (
                "Roominkとの連携を始めます。\n"
                "マイページに表示されている6文字の連携コードを送ってください。\n"
                "10分以内に送信してください。中止する場合は「キャンセル」と送ってください。"
            )
        session = LineRegistrationSession.objects.select_for_update().filter(identity_key=identity).first()
        if session is None:
            return None
        if session.expires_at <= now:
            session.delete()
            return None
        if text == "キャンセル":
            session.delete()
            return "LINE連携を中止しました。再開する場合は「登録」と送ってください。"
        code = text.upper()
        # Even while registering, inquiry text must not receive a code error.
        if not re.fullmatch(r"[A-Z0-9]{6}", code, flags=re.ASCII):
            return None
        casts = Cast.objects.select_for_update().filter(line_link_code=code, line_user_id__isnull=True)
        if store:
            casts = casts.filter(store=store)
        candidates = list(casts[:2])
        # A legacy global webhook must not choose a cast when a code collides.
        if len(candidates) != 1:
            session.failed_attempts += 1
            if session.failed_attempts >= MAX_CODE_ATTEMPTS:
                session.delete()
                return "コードを確認できなかったため、登録を中止しました。マイページのコードを確認し、もう一度「登録」と送ってください。"
            session.save(update_fields=["failed_attempts"])
            return "無効なコードです。マイページの6文字の連携コードをご確認のうえ、再度お試しください。"
        cast = candidates[0]
        cast.line_user_id = user_id
        cast.line_linked_at = now
        try:
            with transaction.atomic():
                cast.save(update_fields=["line_user_id", "line_linked_at"])
        except IntegrityError:
            session.delete()
            return "このLINEはすでにRoominkと連携済みです。マイページで連携状況をご確認ください。"
        session.delete()
        return "連携が完了しました！\nRoominkのマイページを再読み込みすると、連携状況を確認できます。"
