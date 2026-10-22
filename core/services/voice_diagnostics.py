"""Best-effort diagnostics: a storage failure must never interrupt a call."""
import hashlib
import json
import logging
import re

from core.models import VoiceDiagnosticEvent

logger = logging.getLogger(__name__)
FIELDS = ("CallStatus", "DialCallStatus", "DialCallSid", "ParentCallSid", "SequenceNumber",
          "Timestamp", "CallDuration", "DialCallDuration", "SipResponseCode",
          "DialSipResponseCode", "ErrorCode")


def record_voice_event(call, stage, data):
    # Allow only protocol codes/identifiers, never arbitrary text or SIP URIs.
    details = {}
    for key in FIELDS:
        value = str(data.get(key, ""))
        if key.endswith("Sid"):
            valid = re.fullmatch(r"CA[A-Za-z0-9_-]{1,126}", value)
        elif key.endswith("Status"):
            valid = value in {"queued", "initiated", "ringing", "in-progress", "answered", "completed", "busy", "failed", "no-answer", "canceled"}
        elif key == "Timestamp":
            valid = re.fullmatch(r"[A-Za-z0-9: ,+_-]{1,64}", value)
        else:
            valid = re.fullmatch(r"[0-9]{1,8}", value)
        if valid:
            details[key] = value
    sid = str(data.get("CallSid", call.contact_id))[:128]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", sid):
        return
    key = hashlib.sha256(json.dumps([call.pk, stage, sid, details], sort_keys=True).encode()).hexdigest()
    try:
        # Savepoint prevents a failed insert poisoning an enclosing transaction.
        from django.db import transaction
        with transaction.atomic():
            VoiceDiagnosticEvent.objects.get_or_create(event_key=key, defaults={
                "call": call, "stage": stage, "call_sid": sid, "details": details,
            })
    except Exception:
        logger.warning("Voice diagnostic storage failed; CallSid=%s stage=%s", sid, stage)
