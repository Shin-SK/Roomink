import json
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError

from core.models import CallLog


# Only these state transitions and protocol results enter a replay case.
STAGES = {
    "inbound_received", "sip_route_requested", "sip_not_configured", "work_target_requested",
    "sip_progress", "dial_result", "inbound_status", "work_route_requested",
    "work_progress", "work_push_received", "work_callkit_reported",
    "work_callkit_failed", "work_invite", "work_connected", "work_ended",
}
STATUSES = {
    "queued", "initiated", "ringing", "in-progress", "answered", "completed",
    "busy", "failed", "no-answer", "canceled",
}


def replay_case(call, events):
    legs = {call.contact_id: "inbound"}
    timeline = []
    for event in events:
        if event.stage not in STAGES:
            continue
        leg = legs.setdefault(event.call_sid, f"leg-{len(legs)}")
        details = {}
        for field in ("CallStatus", "DialCallStatus"):
            value = event.details.get(field)
            if isinstance(value, str) and value in STATUSES:
                details[field] = value
        for field in ("SipResponseCode", "DialSipResponseCode", "ErrorCode"):
            value = event.details.get(field)
            if isinstance(value, str) and value.isascii() and value.isdecimal() and len(value) <= 8:
                details[field] = value
        timeline.append({
            "at_ms": max(0, (event.received_at - call.created_at) // timedelta(milliseconds=1)),
            "leg": leg,
            "stage": event.stage,
            "details": details,
        })
    return {"version": 1, "clock": "server_observed", "events": timeline}


class Command(BaseCommand):
    help = "Export a de-identified voice diagnostic timeline for staging replay."

    def add_arguments(self, parser):
        parser.add_argument("--store-id", type=int, required=True)
        parser.add_argument("--call-sid", required=True)

    def handle(self, *args, **options):
        try:
            call = CallLog.objects.get(
                store_id=options["store_id"], contact_id=options["call_sid"],
            )
        except CallLog.DoesNotExist as exc:
            raise CommandError("No matching call in this store.") from exc
        events = list(call.diagnostic_events.order_by("received_at", "id")[:501])
        if len(events) > 500:
            raise CommandError("This call exceeds the replay event limit.")
        self.stdout.write(json.dumps(replay_case(call, events), ensure_ascii=False))
