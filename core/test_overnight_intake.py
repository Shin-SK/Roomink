from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch
from django.utils import timezone
from core.tests import RoomankOpsSmokeTestBase
from core.models import CallLog, CallNote


class OvernightIntakeTest(RoomankOpsSmokeTestBase):
    def call(self, store, stamp, **kwargs):
        call = CallLog.objects.create(store=store,contact_id='overnight-'+str(CallLog.objects.count()),from_phone=self.customer.phone,to_phone='05000000001',status='DONE',**kwargs)
        CallLog.objects.filter(pk=call.pk).update(created_at=stamp)
        return call

    def test_history_uses_creation_business_day_and_each_store_boundary(self):
        self.store_b.business_day_boundary_hour=3;self.store_b.save()
        self.manager_a.store_memberships.create(store=self.store_b,role='staff')
        stamp=datetime(2026,10,30,4,0,tzinfo=ZoneInfo('Asia/Tokyo'))
        a=self.call(self.store_a,stamp,customer=self.customer)
        b=self.call(self.store_b,stamp)
        start=self.call(self.store_a,stamp.replace(hour=5)-timedelta(days=1))
        end=self.call(self.store_a,stamp.replace(hour=5))
        c=self.client_as(self.manager_a)
        response=c.get('/api/op/cti/history/?date=2026-10-29')
        self.assertEqual(response.status_code,200)
        self.assertEqual({x['id'] for x in response.data['calls']},{a.pk,start.pk})
        response=c.get('/api/op/cti/history/?date=2026-10-30')
        self.assertEqual({x['id'] for x in response.data['calls']},{b.pk,end.pk})
        self.assertEqual(c.get('/api/op/cti/history/?date=invalid').status_code,400)
        self.assertEqual(c.get('/api/op/cti/history/?offset=-1').status_code,400)
        with patch('core.views.timezone.now', return_value=stamp):
            default=c.get('/api/op/cti/history/')
        self.assertEqual(str(default.data['date']), '2026-10-29')
        self.assertEqual({x['id'] for x in default.data['calls']},{a.pk,start.pk})

    def test_history_pagination_and_context_are_read_only_and_scoped(self):
        stamp=timezone.now()
        calls=[self.call(self.store_a,stamp,customer=self.customer) for _ in range(101)]
        CallNote.objects.create(call=calls[0],body='保存済み問い合わせ',author=self.manager_a)
        c=self.client_as(self.manager_a)
        first=c.get('/api/op/cti/history/')
        self.assertEqual(len(first.data['calls']),100);self.assertTrue(first.data['has_more'])
        tail=c.get('/api/op/cti/history/?offset=100')
        self.assertEqual(len(tail.data['calls']),1);self.assertFalse(tail.data['has_more'])
        before=list(CallLog.objects.values());receipts=calls[0].read_receipts.count()
        ctx=c.get(f'/api/op/cti/calls/{calls[0].pk}/context/')
        self.assertEqual(ctx.status_code,200)
        self.assertEqual(ctx.data['customer_history']['current_notes'][0]['body'],'保存済み問い合わせ')
        self.assertEqual(list(CallLog.objects.values()),before)
        self.assertEqual(calls[0].read_receipts.count(),receipts)
        self.assertEqual(self.client_as(self.manager_b).get(f'/api/op/cti/calls/{calls[0].pk}/context/').status_code,404)

    def test_attention_memo_persists_in_operator_context_only(self):
        c=self.client_as(self.manager_a);path=f'/api/customers/{self.customer.pk}/'
        body={'attention_memo':'70分限定\nAルームNG'}
        self.assertEqual(c.patch(path,body,format='json').status_code,200)
        self.assertEqual(c.get(path).data['attention_memo'],body['attention_memo'])
        self.assertEqual(c.get(path+'reservation-context/').data['attention_memo'],body['attention_memo'])
        call=self.call(self.store_a,timezone.now(),customer=self.customer)
        ctx=c.get(f'/api/op/cti/calls/{call.pk}/context/')
        self.assertEqual(ctx.data['customer_attention']['attention_memo'],body['attention_memo'])
        self.assertEqual(self.client_as(self.manager_b).get(path).status_code,404)
        self.assertIn(self.client_as(self.cast_user_a).get(path).status_code,(403,404))
        self.assertEqual(c.patch(path,{'attention_memo':''},format='json').status_code,200)
        self.assertEqual(c.get(path).data['attention_memo'],'')
