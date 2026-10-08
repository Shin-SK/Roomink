from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections
from django.test import TransactionTestCase, skipUnlessDBFeature

from .models import CallLog, Store, StorePhoneNumber
from .views import _record_inbound_call


@skipUnlessDBFeature("has_select_for_update")
class CtiDeliveryConcurrencyTest(TransactionTestCase):
    def test_simultaneous_first_deliveries_create_one_call(self):
        store = Store.objects.create(name="Concurrent CTI fixture")
        number = StorePhoneNumber.objects.create(store=store, phone="05000000991")
        barrier = Barrier(2)

        def deliver(_):
            close_old_connections()
            try:
                route = StorePhoneNumber.objects.select_related("store").get(pk=number.pk)
                barrier.wait(timeout=10)
                call, created, matches = _record_inbound_call(
                    contact_id="concurrent-delivery", store_phone=route, from_phone="09000000991",
                )
                return call.pk, created, matches
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(deliver, range(2)))
        self.assertEqual(CallLog.objects.count(), 1)
        self.assertEqual(results[0][0], results[1][0])
        self.assertEqual(sum(r[1] for r in results), 1)
        self.assertTrue(all(r[2] for r in results))
