import json
from pathlib import Path

from django.core.management.base import BaseCommand

from core.services.legacy_history_import import import_histories


class Command(BaseCommand):
    help = "旧システムの参照用履歴を取り込む。既定はdry-run。予約・売上・通知は作成しない。"

    def add_arguments(self, parser):
        parser.add_argument("--store-id", type=int, required=True)
        parser.add_argument("--customers", required=True)
        parser.add_argument("--orders", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--expected-fingerprint")

    def handle(self, **options):
        result = import_histories(
            store_id=options["store_id"], customer_bytes=Path(options["customers"]).read_bytes(),
            order_bytes=Path(options["orders"]).read_bytes(), apply=options["apply"],
            expected_fingerprint=options["expected_fingerprint"],
        )
        self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True))
