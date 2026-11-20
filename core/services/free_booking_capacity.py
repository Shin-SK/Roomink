"""Check pending capacity without persisting therapist assignments.

Writers hold the store lock. A snapshot is local to one read/transaction, never
cached between requests or reused after a write.
"""
from datetime import timedelta
from zoneinfo import ZoneInfo

from core.models import Cast, CastUnavailableTime, Course, Customer, Order, ShiftAssignment
from core.services.business_datetime import build_business_interval


class CapacitySearchLimit(Exception):
    pass


def can_place_requests(requests, *, max_steps=20000):
    requests = sorted(requests, key=lambda item: len(item['options']))
    placed, failed_states = [], set()
    steps = 0

    def visit(index):
        nonlocal steps
        steps += 1
        if steps > max_steps:
            raise CapacitySearchLimit
        if index == len(requests):
            return True
        state = (index, tuple(sorted((c, r or 0, q['start'], q['end'], minutes)
                                    for q, c, r, minutes in placed)))
        if state in failed_states:
            return False
        request = requests[index]
        for cast_id, room_id, minutes in request['options']:
            conflict = False
            for other, other_cast, other_room, other_minutes in placed:
                if cast_id == other_cast and (
                    request['start'] < other['end'] + timedelta(minutes=other_minutes)
                    and other['start'] < request['end'] + timedelta(minutes=minutes)
                ):
                    conflict = True
                if room_id is not None and room_id == other_room and (
                    request['start'] < other['end'] and other['start'] < request['end']
                ):
                    conflict = True
                if conflict:
                    break
            if conflict:
                continue
            placed.append((request, cast_id, room_id, minutes))
            if visit(index + 1):
                return True
            placed.pop()
        failed_states.add(state)
        return False

    return visit(0)


def pending_capacity_available(store, *, start, end, course, customer=None,
                               cast=None, exclude_order_id=None, snapshot=None, online=None):
    snapshot = snapshot or CapacitySnapshot(store, start, end, exclude_order_id)
    return snapshot.available(start, end, course, customer, cast, online)


class CapacitySnapshot:
    """Bulk-read a slot-list window once instead of querying for every slot."""

    def __init__(self, store, start, end, exclude_order_id=None):
        self.store = store
        self.casts = list(Cast.objects.filter(store=store, is_booking_queue=False))
        self.margin = timedelta(minutes=max((c.interval_minutes or 0 for c in self.casts), default=0))
        pending = list(Order.objects.filter(store=store, is_free_pending=True,
            status=Order.Status.REQUESTED).exclude(pk=exclude_order_id))
        self.pending, left, right = self.connected(pending, start, end)
        zone = ZoneInfo(store.timezone)
        self.shifts = []
        for shift in ShiftAssignment.objects.filter(store=store, is_absent=False,
            cast__is_booking_queue=False, room__isnull=False,
            date__range=(left.astimezone(zone).date() - timedelta(days=1), right.astimezone(zone).date())):
            begins, ends = build_business_interval(shift.date, shift.start_time, shift.end_time,
                start_day_offset=shift.start_day_offset, end_day_offset=shift.end_day_offset,
                timezone_name=store.timezone)
            self.shifts.append((shift.cast_id, shift.room_id, begins, ends))
        self.orders = list(Order.objects.filter(store=store, status__in=Order.ACTIVE_STATUSES,
            start__lt=right + self.margin, end__gt=left - self.margin).exclude(pk=exclude_order_id))
        self.unavailable = list(CastUnavailableTime.objects.filter(store=store,
            start_at__lt=right, end_at__gt=left))
        self.targets = {c.pk: {cast.pk for cast in c.target_casts.all()}
            for c in Course.objects.filter(store=store).prefetch_related('target_casts')}
        self.customers = {c.pk: (c, {cast.pk for cast in c.ng_casts.all()})
            for c in Customer.objects.filter(pk__in={o.customer_id for o in self.pending})
            .prefetch_related('ng_casts')}

    def connected(self, pending, start, end):
        left, right = start - self.margin, end + self.margin
        connected = []
        while True:
            added = [o for o in pending if o.start < right and o.end > left]
            if not added:
                break
            connected.extend(added)
            selected = {o.pk for o in added}
            pending = [o for o in pending if o.pk not in selected]
            left = min(left, *(o.start - self.margin for o in added))
            right = max(right, *(o.end + self.margin for o in added))
        return connected, left, right

    def available(self, start, end, course, customer=None, cast=None, online=None):
        connected, _, _ = self.connected(list(self.pending), start, end)
        if cast is not None and not connected:
            return True  # Preserve normal manual booking policy outside this pool.
        if customer is not None and customer.pk not in self.customers:
            self.customers[customer.pk] = (customer, set(customer.ng_casts.values_list('pk', flat=True)))
        online = cast is None if online is None else online
        items = [(start, end, course.pk, customer.pk if customer else None, cast, online)] + [
            (o.start, o.end, o.course_id, o.customer_id, None, o.created_by_id is None) for o in connected]
        requests = []
        for begins, ends, course_id, customer_id, fixed, is_online in items:
            targets = self.targets[course_id]
            customer_info = self.customers.get(customer_id)
            options = []
            for candidate in ([fixed] if fixed else self.casts):
                if candidate.is_booking_queue or (targets and candidate.pk not in targets):
                    continue
                if customer_info:
                    person, ng = customer_info
                    if ((is_online and person.online_booking_ng) or
                        (person.flag == Customer.Flag.BAN and
                         (person.ban_type != Customer.BanType.CAST_NG or candidate.pk in ng))):
                        continue
                interval = timedelta(minutes=candidate.interval_minutes or 0)
                if any(o.cast_id == candidate.pk and o.start < ends + interval
                       and begins < o.end + interval for o in self.orders):
                    continue
                if any(u.cast_id == candidate.pk and u.start_at < ends and begins < u.end_at
                       for u in self.unavailable):
                    continue
                for cast_id, room_id, shift_start, shift_end in self.shifts:
                    if cast_id != candidate.pk or shift_start > begins or ends > shift_end:
                        continue
                    if any(o.room_id == room_id and o.start < ends and begins < o.end for o in self.orders):
                        continue
                    options.append((candidate.pk, room_id, candidate.interval_minutes or 0))
            if not options:
                return False
            requests.append({'start': begins, 'end': ends, 'options': sorted(set(options))})
        try:
            return can_place_requests(requests)
        except CapacitySearchLimit:
            return False  # Never accept capacity we could not prove.
