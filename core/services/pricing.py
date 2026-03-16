import math


def recalculate_order_total(order):
    """
    Order の addon snapshot を元に total_price を再計算して保存する。
    呼び出し前に extension_price / nomination_fee_price / discount_amount 等の
    snapshot フィールドが最新であること。
    """
    subtotal = (
        order.course_price
        + order.options_price
        + order.extension_price
        + order.nomination_fee_price
    )

    if order.discount_type_snapshot == "percent":
        order.discount_amount = math.floor(subtotal * order.discount_value_snapshot / 100)
    elif order.discount_type_snapshot == "fixed":
        order.discount_amount = order.discount_value_snapshot
    else:
        order.discount_amount = 0

    order.total_price = max(0, subtotal - order.discount_amount)
    order.save(update_fields=["discount_amount", "total_price", "updated_at"])
