"""Room cash projections. Orders/checkouts remain the only source of business amounts.

An actual count anchors a projection; a price correction changes the projection,
but does not assert that cash was physically received/refunded.
"""
import hashlib
import json
from collections import defaultdict

from django.db.models import Max, Sum

from .business_datetime import business_date_for_datetime, business_day_range
from .reservation_access import card_payment_amount


def cash_source(instance):
    from core.models import Order
    if instance is None:
        return {}
    if isinstance(instance, Order):
        amount = 0
        if instance.status == Order.Status.DONE:
            if instance.payment_method == Order.PaymentMethod.CASH:
                amount = instance.total_price
            elif instance.payment_method == Order.PaymentMethod.CARD:
                amount = card_payment_amount(instance)[1]
        return {
            "source_type": "order", "source_id": instance.pk,
            "room": instance.room_id, "amount": amount,
            "finalized": instance.status == Order.Status.DONE,
            "date": business_date_for_datetime(instance.start, instance.store.timezone).isoformat(),
        }
    return {
        "source_type": "checkout", "source_id": instance.pk,
        "room": instance.room_id,
        # A review/return status does not undo a physical cash handover.
        "amount": instance.cash_returned_to_room_amount - instance.room_cash_taken_amount,
        "taken": instance.room_cash_taken_amount,
        "returned": instance.cash_returned_to_room_amount,
        "date": instance.date.isoformat(),
    }


def record_cash_source_change(before, after, actor_id=None):
    """Called inside the source save transaction; failure rolls back both records."""
    from core.models import RoomCashMovement
    old, new = cash_source(before), cash_source(after)
    if old == new:
        return
    changes = defaultdict(int)
    if old.get("room"):
        changes[(old["room"], old["date"])] -= old["amount"]
    if new.get("room"):
        changes[(new["room"], new["date"])] += new["amount"]
    source = new or old
    adjustment = bool(before and (old.get("finalized") or old.get("taken") or old.get("returned")))
    for (room_id, date), amount in changes.items():
        if not amount:
            continue
        RoomCashMovement.objects.create(
            store_id=(after or before).store_id, room_id=room_id, date=date,
            source_type=source["source_type"], source_id=source["source_id"],
            kind="CORRECTION" if adjustment else ("CASH_SALE" if source["source_type"] == "order" else "HANDOVER"),
            amount=amount, before=old, after=new, recorded_by_id=actor_id,
        )


def _sources(store, d):
    from core.models import Order, CastDailyCheckout
    _, end = business_day_range(d, store.timezone)
    orders = list(Order.objects.filter(store=store, status=Order.Status.DONE, start__lt=end).select_related("store").order_by("pk"))
    checkouts = list(CastDailyCheckout.objects.filter(store=store, date__lte=d).order_by("pk"))
    return orders, checkouts


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def room_cash_summary(store, d, *, room_ids=None, cast_id=None):
    from core.models import Room, RoomCashCheckpoint, RoomCashMovement, RoomCashCount, RoomCashCollection
    from django.utils import timezone

    orders, checkouts = _sources(store, d)
    sources = [cash_source(item) for item in [*orders, *checkouts]]
    by_room = defaultdict(list)
    missing_room = False
    for source in sources:
        if source["room"]:
            by_room[source["room"]].append(source)
        elif source["amount"]:
            missing_room = True
    cast_rows = _cast_rows(store, d, orders, checkouts, only_cast_id=cast_id)
    today = business_date_for_datetime(timezone.now(), store.timezone)
    rows = []
    rooms = Room.objects.filter(store=store)
    if room_ids is not None:
        rooms = rooms.filter(pk__in=room_ids)
    for room in rooms.order_by("sort_order", "id"):
        items = by_room[room.pk]
        source_amount = sum(item["amount"] for item in items)
        collections = RoomCashCollection.objects.filter(store=store, room=room, date__lte=d)
        collection_net = collections.filter(cancelled_at__isnull=True).aggregate(total=Sum("amount"))["total"] or 0
        checkpoint = RoomCashCheckpoint.objects.filter(store=store, room=room, date__lte=d).first()
        legacy = RoomCashCount.objects.filter(store=store, room=room, date__lt=d).order_by("-date").first() if not checkpoint else None
        expected = None
        opening = None
        if checkpoint:
            opening = checkpoint.actual_cash_amount
            expected = opening + source_amount - checkpoint.source_cash_amount - (collection_net - checkpoint.collected_cash_amount)
        elif legacy:
            opening = legacy.actual_cash_amount
            expected = opening + sum(item["amount"] for item in items if item["date"] > legacy.date.isoformat())
            expected -= collections.filter(date__gt=legacy.date, cancelled_at__isnull=True).aggregate(total=Sum("amount"))["total"] or 0
        movements = RoomCashMovement.objects.filter(store=store, room=room, date__lte=d)
        last_movement = movements.aggregate(last=Max("id"))["last"] or 0
        revision = _hash({"sources": items, "checkpoint": checkpoint.pk if checkpoint else None,
                          "legacy": [legacy.pk, legacy.actual_cash_amount, legacy.counted_at.isoformat()] if legacy else None,
                          "movement": last_movement, "collections": [(c.pk, c.amount, c.cancelled_at.isoformat() if c.cancelled_at else None) for c in collections], "date": d.isoformat()})
        history = []
        for movement in movements.order_by("-id")[:30]:
            history.append({
                "id": movement.pk, "kind": movement.kind,
                "label": {"CORRECTION": "記録の訂正による計算変更", "CASH_SALE": "現金売上の計上", "HANDOVER": "退勤の現金受渡記録"}[movement.kind],
                "amount": movement.amount, "created_at": movement.created_at.isoformat(),
                "source_type": movement.source_type, "source_id": movement.source_id,
            })
        for count in RoomCashCheckpoint.objects.filter(store=store, room=room, date__lte=d)[:30]:
            history.append({"id": f"count-{count.pk}", "kind": "COUNT", "label": "実際に数えた現金",
                            "amount": count.actual_cash_amount, "created_at": count.counted_at.isoformat(),
                            "source_type": "count", "source_id": count.pk})
        history = sorted(history, key=lambda item: item["created_at"], reverse=True)[:30]
        corrections = movements.filter(kind="CORRECTION")
        if checkpoint:
            corrections = corrections.filter(id__gt=checkpoint.movement_cursor)
        needs_confirmation = corrections.exists()
        missing_history = False
        if checkpoint:
            recorded_change = movements.filter(id__gt=checkpoint.movement_cursor).aggregate(total=Sum("amount"))["total"] or 0
            # QuerySet.update/bulk imports do not invoke model save. The source
            # still wins; flag the missing history rather than trusting a stale
            # movement total or inventing a physical handover.
            missing_history = source_amount - checkpoint.source_cash_amount != recorded_change
        warnings = []
        if expected is None:
            warnings.append("開始残高が未確認のため、現在残高と不足額は確定できません。実際に数えた現金を一度登録してください。")
        if needs_confirmation:
            warnings.append("記録の訂正で計算額が変わっています。現物の受渡・返金を確認し、必要に応じて数え直してください。")
        if missing_room:
            warnings.append("ルーム未設定の現金記録があります。計算残高に含まれていないため確認してください。")
        if missing_history:
            warnings.append("元の記録と変更履歴に差があります。現金を数えて確認してください。")
        if legacy:
            warnings.append("過去の閉店時カウントを起点にした計算です。現金を数えて現在の残高を確認してください。")
        if d != today:
            warnings.append("選択日の記録を現在の訂正内容で集計した参考値です。実残の登録は本日のみ可能です。")
        day_items = [item for item in items if item["date"] == d.isoformat()]
        cast_data = []
        for cast_row in cast_rows.get(room.pk, []):
            item = dict(cast_row)
            available = item["remaining_receivable_amount"]
            reliable = expected is not None and not missing_room and not item["ambiguous_room"] and not item["settlement_pending"]
            if item["settlement_pending"]:
                warnings.append(f"{item['cast_name']}さんは過去の退勤提出が差戻し中です。未受取額を確認してください。")
            take = min(max(0, expected), max(0, available)) if reliable else None
            item.update({
                "suggested_take_amount": take,
                "projected_room_balance": expected - take if take is not None else None,
                "shortage_amount": max(0, available - take) if take is not None else None,
            })
            cast_data.append(item)
        rows.append({
            "room": room.pk, "room_name": room.name, "balance_known": expected is not None,
            "opening_cash_amount": opening,
            "cash_sales_amount": sum(item["amount"] for item in day_items if item["source_type"] == "order"),
            "room_cash_taken_amount": sum(item.get("taken", 0) for item in day_items),
            "cash_returned_amount": sum(item.get("returned", 0) for item in day_items),
            "expected_cash_amount": expected,
            "actual_cash_amount": checkpoint.actual_cash_amount if checkpoint else (legacy.actual_cash_amount if legacy else None),
            # The discrepancy is fixed at the instant of counting, never compared
            # to a stale physical count after subsequent receipts/handover.
            "difference_amount": (checkpoint.actual_cash_amount - checkpoint.expected_cash_amount) if checkpoint and checkpoint.expected_cash_amount is not None else None,
            "last_counted_at": checkpoint.counted_at.isoformat() if checkpoint else (legacy.counted_at.isoformat() if legacy else None),
            "last_counted_date": checkpoint.date.isoformat() if checkpoint else (legacy.date.isoformat() if legacy else None),
            "memo": checkpoint.memo if checkpoint else (legacy.memo if legacy else ""),
            "revision": revision, "requires_confirmation": needs_confirmation or missing_room or missing_history,
            "can_count": d == today, "warnings": warnings, "history": history,
            "casts": cast_data, "source_cash_amount": source_amount,
            "collected_cash_amount": collection_net,
            "collections": [{"id": c.pk, "amount": c.amount, "memo": c.memo,
                             "recorded_by": c.recorded_by.get_username() if c.recorded_by else "削除済みアカウント",
                             "created_at": c.created_at.isoformat(),
                             "cancelled_at": c.cancelled_at.isoformat() if c.cancelled_at else None,
                             "cancelled_by": c.cancelled_by.get_username() if c.cancelled_by else None}
                            for c in collections.select_related("recorded_by", "cancelled_by")[:30]],
        })
    return rows


def _cast_rows(store, d, orders, checkouts, *, only_cast_id=None):
    from core.models import Cast, CastDailyCheckout, ShiftAssignment
    from core.views import _compute_cast_done_sales, _cast_expense_totals, _cast_carryover_before, _checkout_compensation
    associations = defaultdict(set)
    ids = set()
    for order in orders:
        if business_date_for_datetime(order.start, store.timezone) == d and order.cast_id:
            ids.add(order.cast_id)
            if order.room_id:
                associations[order.cast_id].add(order.room_id)
    for shift in ShiftAssignment.objects.filter(store=store, date=d):
        ids.add(shift.cast_id)
        if shift.room_id:
            associations[shift.cast_id].add(shift.room_id)
    current_checkouts = {item.cast_id: item for item in checkouts if item.date == d}
    for item in current_checkouts.values():
        ids.add(item.cast_id)
        if item.room_id:
            associations[item.cast_id].add(item.room_id)
    rows = defaultdict(list)
    if only_cast_id is not None:
        ids.intersection_update({only_cast_id})
    pending_ids = set(CastDailyCheckout.objects.filter(store=store, date__lt=d, status=CastDailyCheckout.Status.RETURNED).values_list("cast_id", flat=True))
    for cast in Cast.objects.filter(store=store, pk__in=ids).order_by("id"):
        checkout = current_checkouts.get(cast.pk)
        if checkout and checkout.status != checkout.Status.RETURNED:
            compensation = _checkout_compensation(checkout)
        else:
            sales = _compute_cast_done_sales(cast, d)
            compensation = sales["estimated_pay"] - _cast_expense_totals(cast, d, sales["done_count"])["expense_total"]
        opening = _cast_carryover_before(cast, d)
        taken = checkout.room_cash_taken_amount if checkout else 0
        office = checkout.office_cash_paid_amount if checkout else 0
        row = {
            "cast_id": cast.pk, "cast_name": cast.name, "compensation_amount": compensation,
            "carryover_opening_amount": opening, "receivable_amount": opening + compensation,
            "remaining_receivable_amount": opening + compensation - taken - office,
            "room_cash_taken_amount": taken, "office_cash_paid_amount": office,
            "status": checkout.status if checkout else "ESTIMATED",
            "ambiguous_room": len(associations[cast.pk]) != 1,
            "settlement_pending": cast.pk in pending_ids,
        }
        for room_id in associations[cast.pk]:
            rows[room_id].append(row)
    return rows


def save_room_cash_checkpoint(store, d, payload, actor, *, allowed_room_ids=None):
    """Common count write path. Caller holds the store lock inside a transaction."""
    import uuid
    from django.utils import timezone
    from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
    from core.models import Room, RoomCashCheckpoint, RoomCashMovement

    class Conflict(APIException):
        status_code = 409

    if d != business_date_for_datetime(timezone.now(), store.timezone):
        raise ValidationError({"detail": "実残は本日の現在時点でのみ登録できます"})
    try:
        raw_amount, raw_room = payload.get("actual_cash_amount"), payload.get("room")
        for value in (raw_amount, raw_room):
            if isinstance(value, bool) or not isinstance(value, (int, str)) or (isinstance(value, str) and not value.isdecimal()):
                raise ValueError
        room_id, actual_amount = int(raw_room), int(raw_amount)
        request_id = uuid.UUID(str(payload.get("request_id") or ""))
    except (TypeError, ValueError):
        raise ValidationError({"detail": "ルーム・実残高・リクエストIDの形式が不正です"})
    if not 0 <= actual_amount <= 2147483647:
        raise ValidationError({"detail": "実残高は0〜2,147,483,647円の整数で入力してください"})
    if allowed_room_ids is not None and room_id not in allowed_room_ids:
        raise PermissionDenied("本日担当しているルームだけ利用できます")
    room = Room.objects.filter(id=room_id, store=store).first()
    if room is None:
        raise ValidationError({"detail": "対象ルームが見つかりません"})
    memo = payload.get("memo", "") or ""
    if not isinstance(memo, str) or len(memo) > 1000:
        raise ValidationError({"detail": "メモは1000文字以内で入力してください"})
    existing = RoomCashCheckpoint.objects.filter(store=store, request_id=request_id).first()
    if existing:
        if (existing.room_id, existing.actual_cash_amount, existing.memo, existing.date, existing.counted_by_id) != (room_id, actual_amount, memo, d, actor.pk):
            raise Conflict("同じリクエストIDで別のカウントは登録できません")
        return room_id
    row = room_cash_summary(store, d, room_ids={room_id})[0]
    if payload.get("expected_revision") != row["revision"]:
        raise Conflict("現金に関わる記録が更新されています。入力を残したまま最新の内容を確認してください")
    RoomCashCheckpoint.objects.create(
        store=store, room=room, date=d, actual_cash_amount=actual_amount,
        source_cash_amount=row["source_cash_amount"], expected_cash_amount=row["expected_cash_amount"],
        collected_cash_amount=row["collected_cash_amount"],
        source_revision=row["revision"],
        movement_cursor=RoomCashMovement.objects.filter(store=store, room=room).order_by("-id").values_list("id", flat=True).first() or 0,
        request_id=request_id, memo=memo, counted_by=actor,
    )
    return room_id


def save_room_cash_collection(store, d, payload, actor):
    """Caller holds the same store lock as count/source saves."""
    import uuid
    from django.utils import timezone
    from rest_framework.exceptions import APIException, ValidationError
    from core.models import Room, RoomCashCollection

    class Conflict(APIException):
        status_code = 409

    today = business_date_for_datetime(timezone.now(), store.timezone)
    if d != today:
        raise ValidationError({"detail": "回収・取消は現在の営業日で登録してください"})
    raw_room = payload.get("room")
    if isinstance(raw_room, bool) or not str(raw_room).isdecimal():
        raise ValidationError({"detail": "ルームの形式が不正です"})
    room = Room.objects.filter(pk=int(raw_room), store=store).first()
    if not room:
        raise ValidationError({"detail": "対象ルームが見つかりません"})
    operation = payload.get("operation")
    if operation == "collect":
        raw_amount = payload.get("amount")
        if isinstance(raw_amount, bool) or not isinstance(raw_amount, (str, int)) or not str(raw_amount).isdecimal() or not 1 <= int(raw_amount) <= 2147483647:
            raise ValidationError({"detail": "回収額は1〜2,147,483,647円の整数で入力してください"})
        amount = int(raw_amount)
        memo = payload.get("memo", "")
        if not isinstance(memo, str) or len(memo) > 1000:
            raise ValidationError({"detail": "備考は1000文字以内で入力してください"})
        try:
            request_id = uuid.UUID(str(payload.get("request_id", "")))
        except ValueError:
            raise ValidationError({"detail": "リクエストIDが不正です"})
        existing = RoomCashCollection.objects.filter(store=store, request_id=request_id).first()
        if existing:
            if (existing.room_id, existing.amount, existing.memo, existing.recorded_by_id, existing.date) != (room.pk, amount, memo, actor.pk, d):
                raise Conflict("同じリクエストIDで別の回収は登録できません")
            return
    elif operation == "cancel_collection":
        raw_id = payload.get("collection_id")
        if isinstance(raw_id, bool) or not str(raw_id).isdecimal():
            raise ValidationError({"detail": "回収記録が不正です"})
        existing = RoomCashCollection.objects.filter(pk=int(raw_id), store=store, room=room).first()
        if not existing:
            raise ValidationError({"detail": "回収記録が見つかりません"})
        if existing.cancelled_at:
            return
    else:
        raise ValidationError({"detail": "操作が不正です"})
    row = room_cash_summary(store, d, room_ids={room.pk})[0]
    if payload.get("expected_revision") != row["revision"]:
        raise Conflict("現金の情報が更新されました。最新の残高を確認してください")
    if operation == "collect":
        if row["expected_cash_amount"] is None or row["requires_confirmation"]:
            raise ValidationError({"detail": "実際の現金を確認・記録してから回収してください"})
        if amount > row["expected_cash_amount"]:
            raise ValidationError({"detail": "回収額が想定残高を超えています"})
        RoomCashCollection.objects.create(store=store, room=room, date=d, amount=amount, memo=memo, request_id=request_id, recorded_by=actor)
    else:
        # Restoring the net outflow also works when a count was recorded after collection.
        existing.cancelled_at = timezone.now()
        existing.cancelled_by = actor
        existing.save(update_fields=["cancelled_at", "cancelled_by"])


def cast_room_cash_ids(cast, d):
    """Never use another cast's checkout or a stale suggested room for access."""
    from core.models import Room, ShiftAssignment
    from .sales import get_done_orders_for_business_range
    ids = set(ShiftAssignment.objects.filter(store=cast.store, cast=cast, date=d, is_absent=False, room__isnull=False).values_list("room_id", flat=True))
    ids.update(get_done_orders_for_business_range(cast.store, d, d).filter(cast=cast, room__isnull=False).values_list("room_id", flat=True))
    return set(Room.objects.filter(store=cast.store, pk__in=ids).values_list("pk", flat=True))


def cast_room_cash_summary(cast, d, allowed_ids, selected_room=None):
    """Explicit allowlist DTO: no manager memo, history, other cast or store totals."""
    rows = room_cash_summary(cast.store, d, room_ids=({selected_room} if selected_room else allowed_ids), cast_id=cast.pk)
    multiple = len(allowed_ids) > 1
    result = []
    for row in rows:
        safe = {key: row[key] for key in (
            "room", "room_name", "balance_known", "expected_cash_amount", "actual_cash_amount",
            "difference_amount", "last_counted_at", "last_counted_date", "revision", "can_count", "requires_confirmation",
        )}
        # Manager warnings can contain other cast names. Never copy their text.
        safe["warnings"] = []
        if not row["balance_known"]:
            safe["warnings"].append("開始残高が未確認です。実際に数えた現金を登録すると計算残高を確認できます。")
        if row["requires_confirmation"]:
            safe["warnings"].append("計算に確認が必要な記録があります。実際の現金を確認し、不明な場合は店舗へ連絡してください。")
        own = next((item for item in row["casts"] if item["cast_id"] == cast.pk), None)
        safe["settlement"] = None
        if own:
            safe["settlement"] = {key: own[key] for key in (
                "compensation_amount", "carryover_opening_amount", "receivable_amount", "remaining_receivable_amount",
                "room_cash_taken_amount", "office_cash_paid_amount", "suggested_take_amount", "projected_room_balance",
                "shortage_amount", "status", "settlement_pending",
            )}
            if own["settlement_pending"]:
                safe["warnings"].append("過去の退勤提出が差戻し中です。未受取額を店舗へ確認してください。")
            # Explicit room selection allows a trial against that one room;
            # a list of candidates must not silently choose or allocate cash.
            trial_allowed = (selected_room is not None or not multiple) and row["balance_known"] and not own["settlement_pending"] and not row["requires_confirmation"]
            take = min(max(0, row["expected_cash_amount"]), max(0, own["remaining_receivable_amount"])) if trial_allowed else None
            safe["settlement"].update({
                "suggested_take_amount": take,
                "projected_room_balance": row["expected_cash_amount"] - take if take is not None else None,
                "shortage_amount": max(0, own["remaining_receivable_amount"] - take) if take is not None else None,
            })
        result.append(safe)
    return {"date": d.isoformat(), "requires_room_selection": multiple and selected_room is None,
            "selected_room": selected_room or (next(iter(allowed_ids)) if len(allowed_ids) == 1 else None), "rooms": result}
