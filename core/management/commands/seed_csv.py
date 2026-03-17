import csv
import os
from django.core.management.base import BaseCommand
from core.models import Store, Room, Cast, Course, Option, Customer


CSV_DIR = os.path.join(os.path.dirname(__file__), "../../../docs/csv")


class Command(BaseCommand):
    help = "CSVからRoom/Cast/Course/Option/Customerを一括投入"

    def handle(self, *args, **options):
        store = Store.objects.first()
        if not store:
            self.stderr.write("Storeが存在しません。先にmigrateしてください。")
            return

        self._load_rooms(store)
        self._load_casts(store)
        self._load_courses(store)
        self._load_options(store)
        self._load_customers(store)
        self.stdout.write(self.style.SUCCESS("全データ投入完了"))

    def _load_rooms(self, store):
        with open(os.path.join(CSV_DIR, "rooms.csv")) as f:
            for row in csv.DictReader(f):
                Room.objects.update_or_create(
                    store=store, name=row["name"],
                    defaults={"sort_order": int(row["sort_order"])},
                )
        self.stdout.write(f"  Room: {Room.objects.filter(store=store).count()}件")

    def _load_casts(self, store):
        with open(os.path.join(CSV_DIR, "casts.csv")) as f:
            for row in csv.DictReader(f):
                Cast.objects.update_or_create(
                    store=store, name=row["name"],
                    defaults={"avatar_url": row.get("avatar_url", "")},
                )
        self.stdout.write(f"  Cast: {Cast.objects.filter(store=store).count()}件")

    def _load_courses(self, store):
        with open(os.path.join(CSV_DIR, "courses.csv")) as f:
            for row in csv.DictReader(f):
                Course.objects.update_or_create(
                    store=store, name=row["name"],
                    defaults={
                        "duration": int(row["duration"]),
                        "price": int(row["price"]),
                    },
                )
        self.stdout.write(f"  Course: {Course.objects.filter(store=store).count()}件")

    def _load_options(self, store):
        with open(os.path.join(CSV_DIR, "options.csv")) as f:
            for row in csv.DictReader(f):
                Option.objects.update_or_create(
                    store=store, name=row["name"],
                    defaults={"price": int(row["price"])},
                )
        self.stdout.write(f"  Option: {Option.objects.filter(store=store).count()}件")

    def _load_customers(self, store):
        with open(os.path.join(CSV_DIR, "customers.csv")) as f:
            for row in csv.DictReader(f):
                Customer.objects.update_or_create(
                    store=store, phone=row["phone"],
                    defaults={
                        "display_name": row.get("display_name", ""),
                        "flag": row.get("flag", "NONE"),
                        "memo": row.get("memo", ""),
                    },
                )
        self.stdout.write(f"  Customer: {Customer.objects.filter(store=store).count()}件")
