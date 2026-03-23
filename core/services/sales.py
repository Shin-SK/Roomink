import csv
import io
from datetime import timedelta

from django.db.models import Sum, Count


def get_sales_summary(store, date_from, date_to):
    """
    store の DONE 注文を start 日付ベースで集計し、summary dict を返す。
    """
    from ..models import Order

    qs = Order.objects.filter(
        store=store,
        status=Order.Status.DONE,
        start__date__gte=date_from,
        start__date__lte=date_to,
    )

    agg = qs.aggregate(
        total_sales=Sum("total_price"),
        total_orders=Count("id"),
    )
    total_sales = agg["total_sales"] or 0
    total_orders = agg["total_orders"] or 0
    avg_order_value = total_sales // total_orders if total_orders else 0

    # by_day: 期間内の全日を埋める
    day_map = {}
    for row in (
        qs.values("start__date")
        .annotate(sales=Sum("total_price"), orders=Count("id"))
        .order_by("start__date")
    ):
        day_map[row["start__date"]] = {
            "date": row["start__date"].isoformat(),
            "sales": row["sales"],
            "orders": row["orders"],
        }

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
    from ..models import Order

    orders = (
        Order.objects.filter(
            store=store,
            status=Order.Status.DONE,
            start__date__gte=date_from,
            start__date__lte=date_to,
        )
        .select_related("cast", "room", "customer")
        .order_by("start")
    )

    buf = io.StringIO()
    buf.write("\ufeff")  # BOM
    writer = csv.writer(buf)
    writer.writerow([
        "注文ID", "施術日", "顧客名", "キャスト名", "ルーム名",
        "コース名", "コース料金", "オプション料金", "延長料金",
        "指名料", "割引額", "合計金額", "媒体名",
    ])
    for o in orders:
        customer_label = ""
        if o.customer:
            c = o.customer
            customer_label = c.name or c.phone or str(c.pk)
        writer.writerow([
            o.pk,
            o.start.strftime("%Y-%m-%d"),
            customer_label,
            o.cast.name if o.cast else "",
            o.room.name if o.room else "",
            o.course_name,
            o.course_price,
            o.options_price,
            o.extension_price,
            o.nomination_fee_price,
            o.discount_amount,
            o.total_price,
            o.medium_name,
        ])
    return buf.getvalue()
