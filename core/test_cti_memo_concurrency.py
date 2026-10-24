from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections
from django.test import TransactionTestCase, skipUnlessDBFeature
from rest_framework.test import APIClient

from core.models import CallLog, CallNote, Store
from core.tests import make_manager


@skipUnlessDBFeature("has_select_for_update")
class CtiMemoConcurrencyTest(TransactionTestCase):
    def test_simultaneous_retries_create_one_note_and_complete_once(self):
        store = Store.objects.create(name="架空のメモ並行検証店舗")
        manager = make_manager(store, "memo_concurrency_manager")
        call = CallLog.objects.create(store=store, from_phone="09000000991", to_phone="", contact_id="memo-concurrency")
        barrier = Barrier(2)

        def save(_):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(manager)
                barrier.wait(timeout=15)
                response = client.post(
                    f"/api/op/cti/calls/{call.pk}/notes/",
                    {"body": "同じ問い合わせメモ", "complete_reception": True},
                    format="json", HTTP_X_ROOMINK_CALL=str(call.pk),
                )
                return response.status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(save, range(2)))
        self.assertEqual(sorted(statuses), [200, 201])
        self.assertEqual(CallNote.objects.filter(call=call).count(), 1)
        call.refresh_from_db()
        self.assertEqual(call.status, CallLog.Status.DONE)
