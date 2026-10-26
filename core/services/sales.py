import csv
import io
from datetime import timedelta

from django.db.models import Sum, Count

from .compensation import compensation_parts, compensation_total

from .business_datetime import (
    business_date_for_datetime,
    business_day_range,
    format_business_time,
)


def get_done_orders_for_business_range(store, date_from, date_to):
    """指定した営業日範囲のDONE注文QuerySetを返す。"""
    from ..models import Order

    range_start, _ = business_day_range(date_from, store.timezone)
    _, range_end = business_day_range(date_to, store.timezone)
    return Order.objects.filter(
        store=store,
        status=Order.Status.DONE,
        start__gte=range_start,
        start__lt=range_end,
    )


def settlement_store_share(row):
    """現場向けの店落ち表示。保存済みの決済集計・給与には手を加えない。"""
    if row.get("total_sales") is None or row.get("compensation") is None:
        return ""
    return row["total_sales"] - row["compensation"]


def payment_fee_rates(store):
    """決済方法ごとの率を返す。

    カード率は店舗側の原価ではなく、顧客のカード請求額へ上乗せする率として
    使う。現金・PayPay の率だけが店舗側手数料の参考値になる。
    """
    from ..models import Order

    return {
        Order.PaymentMethod.CASH: getattr(store, "cash_fee_rate", 0),
        Order.PaymentMethod.PAYPAY: getattr(store, "paypay_fee_rate", 5),
        Order.PaymentMethod.CARD: getattr(store, "card_fee_rate", 10),
        Order.PaymentMethod.UNSET: 0,
    }


def payment_financial_summary(store, orders):
    """DONE 注文の顧客決済額と店舗側の参考手数料を集計する。

    ``total_sales`` はコース等の元売上、``customer_payment_surcharge`` はカード
    利用者へ上乗せする分、``customer_payment_total`` は両者の合計である。
    カードの上乗せ分を店舗側手数料として二重に控除しないことが重要。
    """
    import math

    from .reservation_access import card_payment_amount
    from ..models import Order

    fee_rates = payment_fee_rates(store)
    total_sales = 0
    customer_payment_surcharge = 0
    payment_fee_estimate = 0

    for order in orders:
        total_sales += order.total_price
        if order.payment_method == Order.PaymentMethod.CARD:
            card_charge, cash_due = card_payment_amount(order)
            # card_charge はオプションを現金受領する場合にその分を含まないため、
            # 現金分を戻して元売上との差額だけを上乗せ額として記録する。
            customer_payment_surcharge += max(0, card_charge + cash_due - order.total_price)
        else:
            rate = fee_rates.get(order.payment_method, 0)
            payment_fee_estimate += math.floor(order.total_price * rate / 100)

    customer_payment_total = total_sales + customer_payment_surcharge
    return {
        "total_sales": total_sales,
        "customer_payment_surcharge": customer_payment_surcharge,
        "customer_payment_total": customer_payment_total,
        "payment_fee_estimate": payment_fee_estimate,
        "net_sales_after_payment_fee": customer_payment_total - payment_fee_estimate,
    }


def payment_parts(order):
    """元売上を実際の決済先へ振り分ける。カード加算は元売上に含めない。"""
    from ..models import Order
    from .reservation_access import card_payment_amount
    if order.payment_method == Order.PaymentMethod.CARD:
        charge, cash = card_payment_amount(order)
        base = order.total_price - cash
        parts = [(Order.PaymentMethod.CARD, base, charge - base)]
        if cash:
            parts.append((Order.PaymentMethod.CASH, cash, 0))
        return parts
    return [(order.payment_method, order.total_price, 0)]


def cash_received_total(orders):
    return sum(sales for order in orders for method, sales, _ in payment_parts(order) if method == "CASH")


def get_sales_summary(store, date_from, date_to):
    """
    store の DONE 注文を営業日ベースで集計し、summary dict を返す。
    """
    qs = get_done_orders_for_business_range(store, date_from, date_to)

    agg = qs.aggregate(
        total_sales=Sum("total_price"),
        total_orders=Count("id"),
    )
    total_sales = agg["total_sales"] or 0
    total_orders = agg["total_orders"] or 0
    avg_order_value = total_sales // total_orders if total_orders else 0

    # by_day: 期間内の全日を埋める
    day_map = {}
    for row in qs.values("start", "total_price"):
        business_date = business_date_for_datetime(row["start"], store.timezone)
        entry = day_map.setdefault(
            business_date,
            {"date": business_date.isoformat(), "sales": 0, "orders": 0},
        )
        entry["sales"] += row["total_price"]
        entry["orders"] += 1

    by_day = []
    d = date_from
    while d <= date_to:
        by_day.append(day_map.get(d, {"date": d.isoformat(), "sales": 0, "orders": 0}))
        d += timedelta(days=1)

    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "total_sales": total_sales,
        "total_orders": total_orders,
        "avg_order_value": avg_order_value,
        "by_day": by_day,
    }


def get_sales_csv(store, date_from, date_to):
    """
    store の DONE 注文明細を CSV 文字列で返す。UTF-8 BOM 付き。
    """
    orders = (
        get_done_orders_for_business_range(store, date_from, date_to)
        .select_related("cast", "room", "customer")
        .order_by("start")
    )

    buf = io.StringIO()
    buf.write("\ufeff")  # BOM
    writer = csv.writer(buf)
    writer.writerow([
        "注文ID", "施術日", "開始時刻", "終了時刻", "顧客名", "顧客電話番号",
        "キャスト名", "ルーム名", "コース名", "コース料金", "オプション料金",
        "延長料金", "指名料", "割引額", "合計金額", "決済方法", "媒体名",
        "実利用者名", "カード請求額（加算含む）", "現金受領額",
    ])
    for o in orders:
        business_date = business_date_for_datetime(o.start, store.timezone)
        customer_label = ""
        customer_phone = ""
        if o.customer:
            c = o.customer
            customer_label = c.display_name or c.phone or str(c.pk)
            customer_phone = c.phone or ""
        writer.writerow([
            o.pk,
            business_date.isoformat(),
            format_business_time(o.start, business_date, store.timezone),
            format_business_time(o.end, business_date, store.timezone),
            customer_label,
            customer_phone,
            o.cast.name if o.cast else "",
            o.room.name if o.room else "",
            o.course_name,
            o.course_price,
            o.options_price,
            o.extension_price,
            o.nomination_fee_price,
            o.discount_amount,
            o.total_price,
            o.get_payment_method_display(),
            o.medium_name,
            o.service_recipient_name,
            sum(sales + surcharge for method, sales, surcharge in payment_parts(o) if method == "CARD"),
            cash_received_total([o]),
        ])
    return buf.getvalue()


def get_sales_dashboard(store, date_from, date_to, cast_id=None, room_id=None, payment_method=None):
    """
    manager向け売上集計ダッシュボード（Phase 3-D）用の集計。
    get_sales_summary() と同じ対象（store の DONE 注文、営業日ベース）を、
    決済方法別/キャスト別（給与見込み込み）/部屋別/日別に内訳集計して返す。
    既存の get_sales_summary() / Sales.vue には影響しない別関数。
    """
    from ..models import Cast, Order, Room, ShiftAssignment

    qs = get_done_orders_for_business_range(store, date_from, date_to)
    if cast_id:
        qs = qs.filter(cast_id=cast_id)
    if room_id:
        qs = qs.filter(room_id=room_id)
    if payment_method:
        qs = qs.filter(payment_method=payment_method)

    agg = qs.aggregate(
        total_sales=Sum("total_price"),
        total_orders=Count("id"),
        course_sales=Sum("course_price"),
        options_sales=Sum("options_price"),
        extension_sales=Sum("extension_price"),
        nomination_fee_sales=Sum("nomination_fee_price"),
        discount_amount=Sum("discount_amount"),
    )

    # 決済方法別。カード率は顧客への上乗せ率であり、店舗側費用としては控除しない。
    fee_rates = payment_fee_rates(store)
    payment_labels = dict(Order.PaymentMethod.choices)
    payment_map = {}
    for order in qs:
        order_summary = payment_financial_summary(store, [order])
        for method, sales, surcharge in payment_parts(order):
            entry = payment_map.setdefault(method, {
                "payment_method": method,
                "payment_method_label": payment_labels.get(method, method),
                "sales": 0, "orders": 0,
                "customer_payment_surcharge": 0, "customer_payment_total": 0,
                "fee_rate": 0 if method == Order.PaymentMethod.CARD else fee_rates.get(method, 0),
                "fee_estimate": 0,
            })
            entry["sales"] += sales
            entry["orders"] += 1
            entry["customer_payment_surcharge"] += surcharge
            entry["customer_payment_total"] += sales + surcharge
            # Preserve the existing store-fee accounting policy. Cash OP from
            # card orders has never incurred a separate estimated cash fee.
            if method == order.payment_method:
                entry["fee_estimate"] += order_summary["payment_fee_estimate"]
    by_payment_method = sorted(payment_map.values(), key=lambda row: -row["sales"])
    for entry in by_payment_method:
        entry["net_sales_after_fee"] = entry["customer_payment_total"] - entry["fee_estimate"]

    payment_summary = payment_financial_summary(store, qs)

    # キャスト別（給与見込みは Phase 2-C / 3-A と同じ計算方針）
    cast_rows = list(
        qs.values("cast_id")
        .annotate(
            sales=Sum("total_price"),
            orders=Count("id"),
            course_sales=Sum("course_price"),
            options_sales=Sum("options_price"),
            extension_sales=Sum("extension_price"),
            nomination_sales=Sum("nomination_fee_price"),
        )
        .order_by("-sales")
    )
    cast_queryset = Cast.objects.filter(store=store).select_related("store")
    if cast_id:
        cast_queryset = cast_queryset.filter(pk=cast_id)
    casts = {c.id: c for c in cast_queryset}
    present_ids = {row["cast_id"] for row in cast_rows}
    attended_shifts = ShiftAssignment.objects.filter(
        store=store, date__range=(date_from, date_to),
        clocked_in_at__isnull=False, is_absent=False,
    )
    if room_id:
        attended_shifts = attended_shifts.filter(room_id=room_id)
    attended_ids = set(attended_shifts.values_list("cast_id", flat=True))
    cast_rows.extend({
        "cast_id": cast.id, "sales": 0, "orders": 0,
        "course_sales": 0, "options_sales": 0, "extension_sales": 0, "nomination_sales": 0,
    } for cast in casts.values() if cast.id in attended_ids and cast.id not in present_ids)
    cast_rows.sort(key=lambda row: (-(row["sales"] or 0), casts[row["cast_id"]].name, row["cast_id"]))
    by_cast = []
    for row in cast_rows:
        cast = casts.get(row["cast_id"])
        if cast is None:
            continue
        course_sales = row["course_sales"] or 0
        options_sales = row["options_sales"] or 0
        by_cast.append({
            "cast_id": cast.id,
            "cast_name": cast.name,
            "orders": row["orders"],
            "sales": row["sales"] or 0,
            "course_sales": course_sales,
            "options_sales": options_sales,
            "course_back_rate": cast.course_back_rate,
            "option_back_rate": cast.option_back_rate,
            "option_fullback_enabled": cast.option_fullback_enabled,
            "estimated_pay": compensation_total(
                cast, course_sales, options_sales, row["nomination_sales"] or 0,
                row["extension_sales"] or 0,
            ),
        })

    # 部屋別
    room_rows = list(
        qs.values("room_id")
        .annotate(sales=Sum("total_price"), orders=Count("id"))
        .order_by("-sales")
    )
    rooms = {r.id: r for r in Room.objects.filter(pk__in=[r["room_id"] for r in room_rows]).select_related("area")}
    by_room = []
    for row in room_rows:
        room = rooms.get(row["room_id"])
        if room is None:
            continue
        by_room.append({
            "room_id": room.id,
            "room_name": room.name,
            "orders": row["orders"],
            "sales": row["sales"] or 0,
        })

    # Group by the immutable attribution, never the room's current area.
    # Legacy rows and roomless/unassigned orders are retained in the unknown bucket.
    area_rows = qs.values("sales_area_id", "sales_area__name").annotate(
        orders=Count("id"), sales=Sum("total_price"),
        course_sales=Sum("course_price"), options_sales=Sum("options_price"),
        extension_sales=Sum("extension_price"), nomination_fee_sales=Sum("nomination_fee_price"),
        discount_amount=Sum("discount_amount"),
    )
    by_area = sorted([
        {
            "area_id": row["sales_area_id"],
            "area_name": row["sales_area__name"] if row["sales_area_id"] else "未設定",
            **{key: row[key] or 0 for key in (
                "orders", "sales", "course_sales", "options_sales",
                "extension_sales", "nomination_fee_sales", "discount_amount",
            )},
        }
        for row in area_rows
    ], key=lambda row: (-row["sales"], row["area_id"] or 0))

    # 日別（期間内の全日を埋める）
    day_map = {}
    for row in qs.values("start", "total_price"):
        business_date = business_date_for_datetime(row["start"], store.timezone)
        entry = day_map.setdefault(
            business_date,
            {"date": business_date.isoformat(), "sales": 0, "orders": 0},
        )
        entry["sales"] += row["total_price"]
        entry["orders"] += 1
    by_day = []
    d = date_from
    while d <= date_to:
        by_day.append(day_map.get(d, {"date": d.isoformat(), "sales": 0, "orders": 0}))
        d += timedelta(days=1)

    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "total_sales": agg["total_sales"] or 0,
        "total_orders": agg["total_orders"] or 0,
        "course_sales": agg["course_sales"] or 0,
        "options_sales": agg["options_sales"] or 0,
        "extension_sales": agg["extension_sales"] or 0,
        "nomination_fee_sales": agg["nomination_fee_sales"] or 0,
        "discount_amount": agg["discount_amount"] or 0,
        "customer_payment_surcharge": payment_summary["customer_payment_surcharge"],
        "customer_payment_total": payment_summary["customer_payment_total"],
        "payment_fee_estimate": payment_summary["payment_fee_estimate"],
        "net_sales_after_payment_fee": payment_summary["net_sales_after_payment_fee"],
        "by_payment_method": by_payment_method,
        "by_cast": by_cast,
        "by_room": by_room,
        "by_area": by_area,
        "by_day": by_day,
    }


def get_sales_cast_detail(
    store,
    date_from,
    date_to,
    cast,
    room_id=None,
    payment_method=None,
):
    """マネージャー向けのキャスト別売上明細を返す。

    売上集計と同じ DONE 注文・営業日判定を使い、予約ごとの売上、報酬見込み、
    店舗配分見込みと、会計項目ごとの小計をまとめる。報酬は日次集計と一致する
    よう、累計額にバック率を掛けた差分を各予約へ配賦する。
    """
    queryset = get_done_orders_for_business_range(store, date_from, date_to).filter(cast=cast)
    if room_id:
        queryset = queryset.filter(room_id=room_id)
    if payment_method:
        queryset = queryset.filter(payment_method=payment_method)
    orders = list(
        queryset.select_related("room", "customer")
        .prefetch_related("options")
        .order_by("start", "id")
    )

    course_map = {}
    option_map = {}
    extension_map = {}
    nomination_map = {}
    discount_map = {}
    medium_map = {}

    def add_amount(target, key, name, amount):
        entry = target.setdefault(
            key,
            {"name": name, "count": 0, "amount": 0},
        )
        entry["count"] += 1
        entry["amount"] += amount

    def add_sales(target, key, name, amount):
        entry = target.setdefault(
            key,
            {"name": name, "count": 0, "sales": 0},
        )
        entry["count"] += 1
        entry["sales"] += amount

    rows = []
    cumulative_course_sales = 0
    cumulative_extension_sales = 0
    cumulative_options_sales = 0
    allocated_course_pay = 0
    allocated_option_pay = 0
    nomination_pay = 0

    for order in orders:
        business_date = business_date_for_datetime(order.start, store.timezone)
        option_names = [option.name for option in order.options.all()]
        option_label = " / ".join(option_names) if option_names else "なし"

        cumulative_course_sales += order.course_price
        cumulative_extension_sales += order.extension_price
        cumulative_options_sales += order.options_price
        parts = compensation_parts(
            cast, cumulative_course_sales, cumulative_options_sales,
            extension_sales=cumulative_extension_sales,
        )
        course_pay_total = parts["course_pay"]
        option_pay_total = parts["option_pay"]
        order_pay = (
            course_pay_total - allocated_course_pay
            + option_pay_total - allocated_option_pay
        )
        if store.nomination_fullback_enabled:
            order_pay += order.nomination_fee_price
            nomination_pay += order.nomination_fee_price
        allocated_course_pay = course_pay_total
        allocated_option_pay = option_pay_total

        financials = payment_financial_summary(store, [order])
        store_allocation = financials["net_sales_after_payment_fee"] - order_pay

        customer_name = order.customer.display_name or order.customer.phone or f"顧客#{order.customer_id}"
        rows.append({
            "order_id": order.id,
            "date": business_date.isoformat(),
            "start_time": format_business_time(order.start, business_date, store.timezone),
            "end_time": format_business_time(order.end, business_date, store.timezone),
            "customer_name": customer_name,
            "customer_id": order.customer_id,
            "room_name": order.room.name if order.room else "未定",
            "course_name": order.course_name,
            "course_price": order.course_price,
            "option_names": option_names,
            "options_price": order.options_price,
            "extension_name": order.extension_name,
            "extension_price": order.extension_price,
            "nomination_fee_name": order.nomination_fee_name,
            "nomination_fee_price": order.nomination_fee_price,
            "discount_name": order.discount_name,
            "discount_amount": order.discount_amount,
            "medium_name": order.medium_name or "未設定",
            "payment_method": order.payment_method,
            "payment_method_label": order.get_payment_method_display(),
            "sales": order.total_price,
            "cash_payment_total": cash_received_total([order]),
            "card_payment_total": sum(sales + surcharge for method, sales, surcharge in payment_parts(order) if method == "CARD"),
            "customer_payment_surcharge": financials["customer_payment_surcharge"],
            "customer_payment_total": financials["customer_payment_total"],
            "estimated_pay": order_pay,
            "store_allocation_estimate": store_allocation,
        })

        add_amount(course_map, order.course_name, order.course_name, order.course_price)
        if order.options_price or option_names:
            add_amount(option_map, option_label, option_label, order.options_price)
        if order.extension_price or order.extension_name:
            name = order.extension_name or "延長"
            add_amount(extension_map, name, name, order.extension_price)
        if order.nomination_fee_price or order.nomination_fee_name:
            name = order.nomination_fee_name or "指名料"
            add_amount(nomination_map, name, name, order.nomination_fee_price)
        if order.discount_amount or order.discount_name:
            name = order.discount_name or "割引"
            add_amount(discount_map, name, name, order.discount_amount)
        add_sales(medium_map, order.medium_name or "未設定", order.medium_name or "未設定", order.total_price)

    payment_summary = payment_financial_summary(store, orders)
    estimated_pay = allocated_course_pay + allocated_option_pay + nomination_pay

    def amount_rows(values):
        return sorted(values.values(), key=lambda row: (-row["amount"], row["name"]))

    return {
        "cast_id": cast.id,
        "cast_name": cast.name,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "totals": {
            "orders": len(orders),
            "sales": payment_summary["total_sales"],
            "customer_payment_surcharge": payment_summary["customer_payment_surcharge"],
            "customer_payment_total": payment_summary["customer_payment_total"],
            "estimated_pay": estimated_pay,
            "store_allocation_estimate": (
                payment_summary["net_sales_after_payment_fee"] - estimated_pay
            ),
        },
        "orders": rows,
        "breakdowns": {
            "courses": amount_rows(course_map),
            "options": amount_rows(option_map),
            "extensions": amount_rows(extension_map),
            "nominations": amount_rows(nomination_map),
            "discounts": amount_rows(discount_map),
            "media": sorted(
                medium_map.values(),
                key=lambda row: (-row["sales"], row["name"]),
            ),
        },
    }


def get_sales_dashboard_csv(store, date_from, date_to, cast_id=None, room_id=None, payment_method=None):
    """get_sales_dashboard() と同じ集計を、セクション区切りのCSV（集計値のみ）で出力する。"""
    data = get_sales_dashboard(store, date_from, date_to, cast_id, room_id, payment_method)

    buf = io.StringIO()
    buf.write("﻿")  # BOM
    writer = csv.writer(buf)

    writer.writerow(["売上集計", f"{data['date_from']} 〜 {data['date_to']}"])
    writer.writerow([])

    writer.writerow(["サマリー"])
    writer.writerow([
        "総売上", "DONE件数", "コース売上", "オプション売上", "延長料金", "指名料", "割引額",
        "カード決済加算(お客様負担)", "お客様決済額", "店舗側決済手数料見込み(参考値)", "手数料差引後売上(参考値)",
    ])
    writer.writerow([
        data["total_sales"], data["total_orders"], data["course_sales"],
        data["options_sales"], data["extension_sales"], data["nomination_fee_sales"],
        data["discount_amount"], data.get("customer_payment_surcharge", 0), data.get("customer_payment_total", data["total_sales"]),
        data.get("payment_fee_estimate", 0), data.get("net_sales_after_payment_fee", data["total_sales"]),
    ])
    writer.writerow([])

    writer.writerow(["決済方法別（カードの率はお客様負担の上乗せ率です）"])
    writer.writerow(["現金払いのOPは現金へ分けて集計。併用した予約は両方の件数に含みます。"])
    writer.writerow(["決済方法", "売上", "件数", "カード決済加算", "お客様決済額", "店舗側手数料率(%)", "店舗側手数料見込み", "手数料差引後売上"])
    for r in data["by_payment_method"]:
        writer.writerow([
            r["payment_method_label"], r["sales"], r["orders"],
            r.get("customer_payment_surcharge", 0), r.get("customer_payment_total", r["sales"]),
            r.get("fee_rate", 0), r.get("fee_estimate", 0), r.get("net_sales_after_fee", r["sales"]),
        ])
    writer.writerow([])

    writer.writerow(["キャスト別"])
    writer.writerow(["キャスト名", "件数", "売上", "コース売上", "オプション売上", "コースバック率(%)", "OPバック率(%)", "給与見込み"])
    for r in data["by_cast"]:
        writer.writerow([
            r["cast_name"], r["orders"], r["sales"], r["course_sales"], r["options_sales"],
            r["course_back_rate"], r["option_back_rate"], r["estimated_pay"],
        ])
    writer.writerow([])

    writer.writerow(["部屋別"])
    writer.writerow(["部屋名", "件数", "売上"])
    for r in data["by_room"]:
        writer.writerow([r["room_name"], r["orders"], r["sales"]])
    writer.writerow([])

    writer.writerow(["エリア別"])
    writer.writerow(["会計完了時のエリア。記録のない過去分は未設定。再集計で過去のエリアは変更しません。"])
    writer.writerow(["エリア名", "件数", "売上", "コース売上", "オプション売上", "延長料金", "指名料", "割引額"])
    for r in data.get("by_area", []):
        writer.writerow([r["area_name"], r["orders"], r["sales"], r["course_sales"], r["options_sales"], r["extension_sales"], r["nomination_fee_sales"], r["discount_amount"]])
    writer.writerow([])

    writer.writerow(["日別"])
    writer.writerow(["日付", "売上", "件数"])
    for r in data["by_day"]:
        writer.writerow([r["date"], r["sales"], r["orders"]])

    return buf.getvalue()
