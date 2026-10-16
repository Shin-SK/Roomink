from core.models import Customer


def customer_booking_blocked(customer, cast_id, *, online=False):
    if online and customer.online_booking_ng:
        return True
    if customer.flag != Customer.Flag.BAN:
        return False
    if customer.ban_type == Customer.BanType.CAST_NG:
        return customer.ng_casts.filter(pk=cast_id).exists()
    return True
