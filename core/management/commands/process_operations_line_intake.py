from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import OperationsCase
from core.services.operations_intake import process_case_triage


class Command(BaseCommand):
    help = "保存済みのRoomink運営LINE本文を一次ヒアリング・Slack案件化する"

    def handle(self, *args, **options):
        cases = OperationsCase.objects.filter(
            triage_requested_at__isnull=False,
        ).select_related("reporter", "store").order_by("triage_requested_at")
        processed = 0
        for case in cases.iterator():
            # 同じ案件への連投を一つの文脈として扱い、最終受信から少し待つ。
            if (timezone.now() - case.triage_requested_at).total_seconds() < 5:
                continue
            process_case_triage(case)
            processed += 1
        self.stdout.write(self.style.SUCCESS(f"operations LINE cases processed: {processed}"))
