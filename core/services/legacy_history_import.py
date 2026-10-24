"""Strict parsing and explicit customer matching for the supplied R.s SPA exports."""
import csv
import hashlib
import io
import re
from collections import Counter, defaultdict
from datetime import datetime

from django.core.management.base import CommandError
from django.db import transaction

from core.models import Customer, LegacyCustomerHistory, Store
from core.utils.phone import normalize_phone

CUSTOMER_HEADERS = ["No", "ID", "名前", "電話番号", "電話番号2", "メールアドレス", "住所", "備考"]
ORDER_HEADERS = ["No", "顧客ID", "顧客名", "日時", "スタート時間", "受付者", "セラピスト", "コース", "指名", "延長", "割引", "割引料金", "オプション", "交通費", "媒体", "支払", "料金", "セラピスト", "お店", "備考"]
SOURCE = "rs-spa-20261024"


def parse_exports(customer_bytes, order_bytes):
    def read(raw, headers):
        try:
            rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline="")))
        except (UnicodeError, csv.Error) as exc:
            raise CommandError("CSVを読み込めません。UTF-8形式を確認してください。") from exc
        if not rows or rows[0] != headers:
            raise CommandError("CSVの列が想定と異なります。取込を停止しました。")
        if any(len(row) != len(headers) for row in rows[1:]):
            raise CommandError("CSVの列数が一致しません。")
        return [[value.strip() for value in row] for row in rows[1:]]

    customers = {}
    for row in read(customer_bytes, CUSTOMER_HEADERS):
        if not row[1] or row[1] in customers:
            raise CommandError("顧客IDが空欄または重複しています。")
        customers[row[1]] = row
    histories = defaultdict(list)
    order_numbers = set()
    summary_rows = 0
    for row in read(order_bytes, ORDER_HEADERS):
        if not row[0] and not row[1] and all(not row[i] for i in (2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15, 19)):
            summary_rows += 1
            continue
        if not row[0] or row[0] in order_numbers or row[1] not in customers:
            raise CommandError("オーダー番号の重複または参照先のない顧客があります。")
        try:
            day = datetime.strptime(row[3], "%Y/%m/%d").date().isoformat()
        except ValueError as exc:
            raise CommandError("日時を解釈できないオーダーがあります。") from exc
        if not re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", row[4]) or not row[7]:
            raise CommandError("開始時刻またはコースを確認できません。")
        if not re.fullmatch(r"[\d,]+", row[16]):
            raise CommandError("料金を解釈できないオーダーがあります。")
        order_numbers.add(row[0])
        histories[row[1]].append({
            "source_order": row[0], "date": day, "time": row[4],
            "therapist": row[6], "course": row[7], "nomination": row[8],
            "extension": row[9], "discount": row[10], "discount_charge": row[11],
            "options": row[12], "payment": row[15], "charge": row[16], "memo": row[19],
        })
    if not histories:
        raise CommandError("取り込むオーダーがありません。")
    for entries in histories.values():
        entries.sort(key=lambda e: (e["date"], e["time"], int(e["source_order"])), reverse=True)
    fingerprint = hashlib.sha256(customer_bytes + b"\x00" + order_bytes).hexdigest()
    return customers, dict(histories), fingerprint, summary_rows


def import_histories(*, store_id, customer_bytes, order_bytes, apply=False, expected_fingerprint=None):
    source_customers, histories, fingerprint, summary_rows = parse_exports(customer_bytes, order_bytes)
    if apply and expected_fingerprint != fingerprint:
        raise CommandError("事前確認したファイルと一致しません。dry-runのfingerprintを指定してください。")
    with transaction.atomic():
        store_qs = Store.objects.select_for_update() if apply else Store.objects
        store = store_qs.get(pk=store_id)
        existing_customers = list(Customer.objects.filter(store=store))
        by_legacy = defaultdict(list)
        by_phone = defaultdict(list)
        for customer in existing_customers:
            by_phone[customer.phone].append(customer)
            match = re.search(r"旧顧客ID:\s*([^\n]+)", customer.staff_memo or "")
            if match:
                for legacy_id in re.findall(r"\d+", match.group(1)):
                    by_legacy[legacy_id].append(customer)
        source_phones = Counter(normalize_phone(source_customers[key][3]) for key in histories)
        existing = {item.legacy_customer_id: item for item in LegacyCustomerHistory.objects.filter(store=store, source=SOURCE)}
        pending = []
        counts = Counter()
        for legacy_id, entries in histories.items():
            row = source_customers[legacy_id]
            phone = normalize_phone(row[3])
            candidates = by_legacy[legacy_id]
            customer = None
            reason = "unmatched"
            if len(candidates) == 1:
                customer, reason = candidates[0], "legacy_id"
            elif candidates:
                reason = "ambiguous_legacy_id"
            elif len(phone) in (10, 11) and phone.startswith("0"):
                matches = by_phone[phone]
                if len(matches) == 1 and source_phones[phone] == 1:
                    customer, reason = matches[0], "unique_phone"
                elif matches or source_phones[phone] > 1:
                    reason = "ambiguous_phone"
            else:
                reason = "invalid_phone"
            counts["linked_customers" if customer else "unlinked_customers"] += 1
            counts["linked_orders" if customer else "unlinked_orders"] += len(entries)
            if legacy_id in existing:
                item = existing[legacy_id]
                if item.source_fingerprint != fingerprint or item.entries != entries:
                    raise CommandError("保存済み履歴と内容が異なります。自動上書きはしません。")
                counts["unchanged"] += 1
            else:
                pending.append(LegacyCustomerHistory(
                    store=store, customer=customer, source=SOURCE, legacy_customer_id=legacy_id,
                    display_name=row[2], phone=row[3], entries=entries,
                    source_fingerprint=fingerprint, link_reason=reason,
                ))
        if apply:
            LegacyCustomerHistory.objects.bulk_create(pending)
        return {
            "fingerprint": fingerprint, "source_customers": len(source_customers),
            "history_customers": len(histories), "orders": sum(map(len, histories.values())),
            "excluded_summary_rows": summary_rows, "created" if apply else "would_create": len(pending),
            "applied": apply, **dict(counts),
        }
