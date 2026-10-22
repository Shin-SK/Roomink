import json

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime

from core.models import CallLog


class Command(BaseCommand):
    help = "内部用: 店舗と通話IDまたは日時から診断記録を表示（電話番号・顧客情報なし）"

    def add_arguments(self, parser):
        parser.add_argument("--store-id", type=int, required=True)
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--call-sid")
        group.add_argument("--since", help="タイムゾーン付きISO日時")

    def handle(self, *args, **options):
        calls = CallLog.objects.filter(store_id=options["store_id"])
        if options["call_sid"]:
            calls = calls.filter(contact_id=options["call_sid"])
        else:
            from django.utils.timezone import is_naive
            try:
                since = parse_datetime(options["since"])
            except ValueError:
                since = None
            if since is None or is_naive(since):
                raise CommandError("--since はタイムゾーン付きISO日時で指定してください")
            calls = calls.filter(created_at__gte=since)
        for call in calls.order_by("created_at")[:100]:
            self.stdout.write(json.dumps({
                "call_sid": call.contact_id, "store_id": call.store_id,
                "received_at": call.created_at.isoformat(),
                "events": [{"stage": event.stage, "call_sid": event.call_sid,
                            "received_at": event.received_at.isoformat(), "details": event.details}
                           for event in call.diagnostic_events.order_by("received_at", "id")],
            }, ensure_ascii=False))
