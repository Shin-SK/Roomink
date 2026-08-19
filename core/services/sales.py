import csv
import io
from datetime import timedelta

from django.db.models import Sum, Count

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


def payment_fee_rates(store):
    """決済方法ごとの手数料率（%・参考値）を返す。Store設定が未設定/存在しない場合は固定値にフォールバックする。
    現金0% / PayPay5% / カード10% / 未設定0%。給与確定・支払い処理・DailySettlementViewには一切接続しない。"""
    from ..models import Order

    return {
        Order.PaymentMethod.CASH: getattr(store, "cash_fee_rate", 0),
        Order.PaymentMethod.PAYPAY: getattr(store, "paypay_fee_rate", 5),
        Order.PaymentMethod.CARD: getattr(store, "card_fee_rate", 10),
        Order.PaymentMethod.UNSET: 0,
    }


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
        "実利用者名",
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
        ])
    return buf.getvalue()


def get_sales_dashboard(store, date_from, date_to, cast_id=None, room_id=None, payment_method=None):
    """
    manager向け売上集計ダッシュボード（Phase 3-D）用の集計。
    get_sales_summary() と同じ対象（store の DONE 注文、営業日ベース）を、
    決済方法別/キャスト別（給与見込み込み）/部屋別/日別に内訳集計して返す。
    既存の get_sales_summary() / Sales.vue には影響しない別関数。
    """
    import math

    from ..models import Cast, Order, Room

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

    # 決済方法別（決済手数料は参考値。確定精算・給与確定には接続しない）
    fee_rates = payment_fee_rates(store)
    payment_labels = dict(Order.PaymentMethod.choices)
    by_payment_method = []
    total_fee_estimate = 0
    for row in (
        qs.values("payment_method")
        .annotate(sales=Sum("total_price"), orders=Count("id"))
        .order_by("-sales")
    ):
        pm = row["payment_method"]
        sales = row["sales"] or 0
        fee_rate = fee_rates.get(pm, 0)
        fee_estimate = math.floor(sales * fee_rate / 100)
        total_fee_estimate += fee_estimate
        by_payment_method.append({
            "payment_method": pm,
            "payment_method_label": payment_labels.get(pm, pm),
            "sales": sales,
            "orders": row["orders"],
            "fee_rate": fee_rate,
            "fee_estimate": fee_estimate,
            "net_sales_after_fee": sales - fee_estimate,
        })

    # キャスト別（給与見込みは Phase 2-C / 3-A と同じ計算方針）
    cast_rows = list(
        qs.values("cast_id")
        .annotate(
            sales=Sum("total_price"),
            orders=Count("id"),
            course_sales=Sum("course_price"),
            options_sales=Sum("options_price"),
        )
        .order_by("-sales")
    )
    casts = {c.id: c for c in Cast.objects.filter(pk__in=[r["cast_id"] for r in cast_rows])}
    by_cast = []
    for row in cast_rows:
        cast = casts.get(row["cast_id"])
        if cast is None:
            continue
        course_sales = row["course_sales"] or 0
        options_sales = row["options_sales"] or 0
        course_back = math.floor(course_sales * cast.course_back_rate / 100)
        option_back = math.floor(options_sales * cast.option_back_rate / 100)
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
            "estimated_pay": course_back + option_back,
        })

    # 部屋別
    room_rows = list(
        qs.values("room_id")
        .annotate(sales=Sum("total_price"), orders=Count("id"))
        .order_by("-sales")
    )
    rooms = {r.id: r for r in Room.objects.filter(pk__in=[r["room_id"] for r in room_rows])}
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

    # エリア別（Room.area_name ベース。空欄は「未設定」扱い。給与見込みは含めない＝キャスト単位ではないため）
    area_map = {}
    for row in room_rows:
        room = rooms.get(row["room_id"])
        if room is None:
            continue
        area_key = room.area_name or "未設定"
        entry = area_map.setdefault(area_key, {
            "area_name": area_key,
            "orders": 0,
            "sales": 0,
            "course_sales": 0,
            "options_sales": 0,
        })
        entry["orders"] += row["orders"]
        entry["sales"] += row["sales"] or 0
    # コース/オプション売上はエリア（部屋グループ）単位で別集計する
    area_detail_rows = list(
        qs.values("room_id")
        .annotate(course_sales=Sum("course_price"), options_sales=Sum("options_price"))
    )
    for row in area_detail_rows:
        room = rooms.get(row["room_id"])
        if room is None:
            continue
        area_key = room.area_name or "未設定"
        entry = area_map.get(area_key)
        if entry is None:
            continue
        entry["course_sales"] += row["course_sales"] or 0
        entry["options_sales"] += row["options_sales"] or 0
    by_area = sorted(area_map.values(), key=lambda r: -r["sales"])

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
        "payment_fee_estimate": total_fee_estimate,
        "net_sales_after_payment_fee": (agg["total_sales"] or 0) - total_fee_estimate,
        "by_payment_method": by_payment_method,
        "by_cast": by_cast,
        "by_room": by_room,
        "by_area": by_area,
        "by_day": by_day,
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
        "決済手数料見込み(参考値)", "手数料差引後売上(参考値)",
    ])
    writer.writerow([
        data["total_sales"], data["total_orders"], data["course_sales"],
        data["options_sales"], data["extension_sales"], data["nomination_fee_sales"],
        data["discount_amount"],
        data.get("payment_fee_estimate", 0), data.get("net_sales_after_payment_fee", data["total_sales"]),
    ])
    writer.writerow([])

    writer.writerow(["決済方法別（手数料は参考値。確定精算・給与確定には接続しません）"])
    writer.writerow(["決済方法", "売上", "件数", "手数料率(%)", "手数料見込み", "手数料差引後売上"])
    for r in data["by_payment_method"]:
        writer.writerow([
            r["payment_method_label"], r["sales"], r["orders"],
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
    writer.writerow(["エリア名", "件数", "売上", "コース売上", "オプション売上"])
    for r in data.get("by_area", []):
        writer.writerow([r["area_name"], r["orders"], r["sales"], r["course_sales"], r["options_sales"]])
    writer.writerow([])

    writer.writerow(["日別"])
    writer.writerow(["日付", "売上", "件数"])
    for r in data["by_day"]:
        writer.writerow([r["date"], r["sales"], r["orders"]])

    return buf.getvalue()
