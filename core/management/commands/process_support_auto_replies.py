from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import SupportConversation, SupportMessage


class Command(BaseCommand):
    help = "確認期限を過ぎた安全な問い合わせ返信案をアプリ内へ送信する"

    def handle(self, *args, **options):
        if not settings.SUPPORT_AUTO_REPLY_ENABLED:
            self.stdout.write("SUPPORT_AUTO_REPLY_ENABLED is disabled")
            return

        conversations = SupportConversation.objects.filter(
            status=SupportConversation.Status.ESCALATED,
            auto_reply_scheduled_at__lte=timezone.now(),
            auto_reply_sent_at__isnull=True,
            auto_reply_cancelled_at__isnull=True,
        ).exclude(ai_reply_draft="")
        sent = 0
        for conversation in conversations.iterator():
            SupportMessage.objects.create(
                conversation=conversation,
                role=SupportMessage.Role.ASSISTANT,
                content=conversation.ai_reply_draft,
            )
            conversation.status = SupportConversation.Status.RESOLVED
            conversation.resolved_at = timezone.now()
            conversation.auto_reply_sent_at = timezone.now()
            conversation.auto_reply_scheduled_at = None
            conversation.save(update_fields=[
                "status", "resolved_at", "auto_reply_sent_at",
                "auto_reply_scheduled_at", "updated_at",
            ])
            sent += 1
        self.stdout.write(self.style.SUCCESS(f"support auto replies sent: {sent}"))
