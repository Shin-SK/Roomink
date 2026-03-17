from django.core.management.base import BaseCommand
from core.models import Store, Room, Cast, Course, Option, Customer


ROOMS = [
    {"name": "Room A", "sort_order": 1},
    {"name": "Room B", "sort_order": 2},
    {"name": "Room C", "sort_order": 3},
    {"name": "Room D", "sort_order": 4},
    {"name": "Room E", "sort_order": 5},
    {"name": "VIPルーム", "sort_order": 6},
]

CASTS = [
    "あかり", "みさき", "ゆうな", "れいな", "さくら",
    "ひなた", "まお", "りこ", "えみ", "ななせ",
]

COURSES = [
    {"name": "40分コース", "duration": 40, "price": 5000},
    {"name": "60分コース", "duration": 60, "price": 8000},
    {"name": "90分コース", "duration": 90, "price": 12000},
    {"name": "120分コース", "duration": 120, "price": 16000},
    {"name": "180分コース", "duration": 180, "price": 22000},
    {"name": "フリータイム", "duration": 240, "price": 30000},
]

OPTIONS = [
    {"name": "シャンパン", "price": 5000},
    {"name": "ワインボトル", "price": 8000},
    {"name": "フルーツ盛り", "price": 3000},
    {"name": "カラオケ", "price": 2000},
    {"name": "写真撮影", "price": 1500},
]

CUSTOMERS = [
    {"phone": "09012345678", "display_name": "田中太郎", "flag": "NONE", "memo": "常連のお客様"},
    {"phone": "09087654321", "display_name": "山田花子", "flag": "ATTENTION", "memo": "要注意"},
    {"phone": "08011112222", "display_name": "佐藤一郎", "flag": "NONE", "memo": ""},
    {"phone": "07033334444", "display_name": "鈴木次郎", "flag": "NONE", "memo": "友人紹介あり"},
    {"phone": "09055556666", "display_name": "高橋三郎", "flag": "NONE", "memo": "VIP"},
    {"phone": "08077778888", "display_name": "伊藤四郎", "flag": "NONE", "memo": "月2回ペース"},
    {"phone": "09099990000", "display_name": "渡辺五郎", "flag": "BAN", "memo": "出禁"},
    {"phone": "07011223344", "display_name": "中村六郎", "flag": "NONE", "memo": "初回来店"},
    {"phone": "09055667788", "display_name": "小林七郎", "flag": "NONE", "memo": ""},
    {"phone": "08099001122", "display_name": "加藤八郎", "flag": "ATTENTION", "memo": "遅刻多い"},
]


class Command(BaseCommand):
    help = "初期データを一括投入"

    def handle(self, *args, **options):
        store = Store.objects.first()
        if not store:
            self.stderr.write("Storeが存在しません。先にmigrateしてください。")
            return

        for r in ROOMS:
            Room.objects.update_or_create(store=store, name=r["name"], defaults={"sort_order": r["sort_order"]})
        self.stdout.write(f"  Room: {len(ROOMS)}件")

        for name in CASTS:
            Cast.objects.update_or_create(store=store, name=name, defaults={"avatar_url": ""})
        self.stdout.write(f"  Cast: {len(CASTS)}件")

        for c in COURSES:
            Course.objects.update_or_create(store=store, name=c["name"], defaults={"duration": c["duration"], "price": c["price"]})
        self.stdout.write(f"  Course: {len(COURSES)}件")

        for o in OPTIONS:
            Option.objects.update_or_create(store=store, name=o["name"], defaults={"price": o["price"]})
        self.stdout.write(f"  Option: {len(OPTIONS)}件")

        for cu in CUSTOMERS:
            Customer.objects.update_or_create(store=store, phone=cu["phone"], defaults={
                "display_name": cu["display_name"], "flag": cu["flag"], "memo": cu["memo"],
            })
        self.stdout.write(f"  Customer: {len(CUSTOMERS)}件")

        self.stdout.write(self.style.SUCCESS("全データ投入完了"))
