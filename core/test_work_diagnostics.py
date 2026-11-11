import uuid

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import CallLog, VoiceDiagnosticEvent, WorkDiagnosticEvent
from .test_work_devices import WorkDeviceFoundationTest


class WorkDiagnosticsTest(TestCase):
    setUp = WorkDeviceFoundationTest.setUp
    personal_login = WorkDeviceFoundationTest.personal_login
    device_client = WorkDeviceFoundationTest.device_client

    def test_batch_retry_privacy_and_tenant_boundary(self):
        token = self.personal_login().data["token"]
        client = self.device_client(token)
        sid = "CA" + "1" * 32
        call = CallLog.objects.create(
            store=self.store_a, contact_id=sid, from_phone="09012345678",
        )
        event = {
            "event_id": str(uuid.uuid4()), "call_sid": sid, "stage": "callkit_failed",
            "observed_at": timezone.now().isoformat(),
            "snapshot": {"os": "18.0", "app_state": "background", "error_code": 3,
                         "phone": "09012345678", "token": "must-not-persist"},
        }
        for _ in range(2):
            response = client.post("/api/work/diagnostics/", {"events": [event]}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(WorkDiagnosticEvent.objects.count(), 1)
        self.assertNotIn("phone", WorkDiagnosticEvent.objects.get().snapshot)
        self.assertNotIn("token", WorkDiagnosticEvent.objects.get().snapshot)
        manager = APIClient()
        manager.force_authenticate(self.manager)
        result = manager.get("/api/op/work-diagnostics/", {"call_id": call.pk})
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data["device_observation"], "observed")
        self.assertNotIn(sid, str(result.data["replay"]))
        self.assertNotIn("09012345678", str(result.data))
        manager.force_authenticate(self.outsider)
        self.assertEqual(manager.get("/api/op/work-diagnostics/", {"call_id": call.pk}).status_code, 404)

    def test_child_sid_correlation_and_unobserved(self):
        call = CallLog.objects.create(
            store=self.store_a, contact_id="CA" + "2" * 32,
        )
        manager = APIClient()
        manager.force_authenticate(self.manager)
        initial = manager.get("/api/op/work-diagnostics/", {"call_id": call.pk})
        self.assertEqual(initial.data["device_observation"], "unobserved")
        token = self.personal_login().data["token"]
        child_sid = "CA" + "3" * 32
        VoiceDiagnosticEvent.objects.create(
            call=call, event_key="child", stage="work_progress", call_sid=child_sid,
        )
        payload = {"events": [{
            "event_id": str(uuid.uuid4()), "call_sid": child_sid, "stage": "push_received",
            "observed_at": timezone.now().isoformat(), "snapshot": {},
        }]}
        self.assertEqual(self.device_client(token).post(
            "/api/work/diagnostics/", payload, format="json",
        ).status_code, 200)
        result = manager.get("/api/op/work-diagnostics/", {"call_id": call.pk})
        self.assertEqual(result.data["devices"][0]["stage"], "push_received")
        self.assertEqual(result.data["replay"]["device_events"][0]["device"], "device-1")

    def test_reject_invalid_and_unauthenticated_batches(self):
        token = self.personal_login().data["token"]
        invalid = {"events": [{
            "event_id": str(uuid.uuid4()), "stage": "raw_payload", "snapshot": {},
            "observed_at": timezone.now().isoformat(),
        }]}
        self.assertEqual(self.device_client(token).post(
            "/api/work/diagnostics/", invalid, format="json",
        ).status_code, 400)
        self.assertIn(APIClient().post("/api/work/diagnostics/", invalid, format="json").status_code, [401, 403])
