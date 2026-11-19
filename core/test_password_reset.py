from datetime import datetime, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from core.models import Store, UserProfile


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', FRONTEND_URL='https://roomink.example', PASSWORD_RESET_TIMEOUT=1800)
class PasswordResetTest(TestCase):
    initial = 'Initial-QA-Only-Password-93751'
    changed = 'Changed-QA-Only-Password-52917'

    def setUp(self):
        cache.clear()
        self.user=get_user_model().objects.create_superuser('recovery-admin', 'recovery@example.com', self.initial)
        self.client=APIClient()
        self.store=Store.objects.create(name='復旧テスト')

    def link(self, user=None):
        user=user or self.user
        return {'uid':urlsafe_base64_encode(force_bytes(user.pk)),'token':default_token_generator.make_token(user)}

    def confirm(self, link=None, password=None, client=None):
        password = self.changed if password is None else password
        return (client or self.client).post('/api/auth/password-reset/confirm/',{**(link or self.link()),'new_password':password,'new_password_confirm':password},format='json')

    def test_request_only_sends_to_registered_email_and_never_changes_password(self):
        r=self.client.post('/api/auth/password-reset/',{'username':self.user.username,'email':'attacker@example.com','new_password':self.changed},format='json',HTTP_HOST='testserver')
        self.assertEqual(r.status_code,200)
        self.assertEqual(len(mail.outbox),1)
        self.assertEqual(mail.outbox[0].to,['recovery@example.com'])
        url=next(x for x in mail.outbox[0].body.splitlines() if x.startswith('https://'))
        parsed=urlsplit(url)
        self.assertEqual(parsed.netloc,'roomink.example')
        self.assertEqual(parsed.path,'/password-reset')
        self.assertEqual(parsed.query,'')
        values=parse_qs(parsed.fragment)
        self.assertIn('uid',values);self.assertIn('token',values)
        self.assertNotIn(self.changed,mail.outbox[0].body)
        self.user.refresh_from_db();self.assertTrue(self.user.check_password(self.initial))

    def test_missing_inactive_no_email_and_unusable_accounts_have_same_response(self):
        inactive=get_user_model().objects.create_user('inactive',email='inactive@example.com',password=self.initial,is_active=False)
        no_email=get_user_model().objects.create_user('no-mail',password=self.initial)
        unusable=get_user_model().objects.create_user('unusable',email='unusable@example.com');unusable.set_unusable_password();unusable.save()
        results=[]
        for username in [self.user.username,'absent',inactive.username,no_email.username,unusable.username]:
            r=self.client.post('/api/auth/password-reset/',{'username':username},format='json');self.assertEqual(r.status_code,200);results.append(r.json())
        self.assertTrue(all(r==results[0] for r in results))
        self.assertEqual(len(mail.outbox),1)

    def test_email_delivery_failure_is_not_exposed_and_password_is_unchanged(self):
        with patch('core.services.password_reset.send_mail',side_effect=RuntimeError('sensitive SMTP failure')):
            r=self.client.post('/api/auth/password-reset/',{'username':self.user.username},format='json')
        self.assertEqual(r.status_code,200);self.assertNotIn('SMTP',str(r.json()))
        self.user.refresh_from_db();self.assertTrue(self.user.check_password(self.initial))

    def test_repeated_requests_are_cooled_down(self):
        for _ in range(2):self.assertEqual(self.client.post('/api/auth/password-reset/',{'username':self.user.username},format='json').status_code,200)
        self.assertEqual(len(mail.outbox),1)

    def test_request_throttle(self):
        for n in range(5):self.assertEqual(self.client.post('/api/auth/password-reset/',{'username':'missing'+str(n)},format='json').status_code,200)
        self.assertEqual(self.client.post('/api/auth/password-reset/',{'username':'missing6'},format='json').status_code,429)

    def test_confirm_throttle(self):
        for _ in range(10):self.assertEqual(self.client.post('/api/auth/password-reset/validate/',{'uid':'bad','token':'bad'},format='json').status_code,400)
        self.assertEqual(self.client.post('/api/auth/password-reset/validate/',{'uid':'bad','token':'bad'},format='json').status_code,429)

    def test_valid_link_changes_password_once_and_invalidates_old_sessions(self):
        session=APIClient();session.force_login(self.user)
        link=self.link();r=self.confirm(link);self.assertEqual(r.status_code,200,r.data)
        self.user.refresh_from_db();self.assertTrue(self.user.check_password(self.changed))
        self.assertEqual(self.confirm(link).status_code,400)
        self.assertEqual(session.get('/api/auth/me/').status_code,403)
        self.assertEqual(self.client.post('/api/auth/login/',{'username':self.user.username,'password':self.initial},format='json').status_code,401)
        self.assertEqual(self.client.post('/api/auth/login/',{'username':self.user.username,'password':self.changed},format='json').status_code,200)

    def test_superuser_policy_is_returned_and_enforced(self):
        link=self.link();r=self.client.post('/api/auth/password-reset/validate/',link,format='json')
        self.assertEqual(r.status_code,200);self.assertEqual(r.data['min_length'],20)
        self.assertEqual(self.confirm(link,'Valid-QA-12345').status_code,400)
        self.assertEqual(self.confirm(link).status_code,200)

    def test_verified_reset_clears_only_the_target_accounts_lockout(self):
        from axes.models import AccessAttempt
        for _ in range(5):self.client.post('/api/auth/login/',{'username':self.user.username,'password':'incorrect'},format='json')
        self.assertTrue(AccessAttempt.objects.filter(username=self.user.username,failures_since_start__gte=5).exists())
        self.assertEqual(self.confirm().status_code,200)
        self.assertFalse(AccessAttempt.objects.filter(username=self.user.username).exists())
        self.assertEqual(self.client.post('/api/auth/login/',{'username':self.user.username,'password':self.changed},format='json').status_code,200)

    def test_role_policies_and_other_accounts_are_preserved(self):
        for role,length in [('manager',10),('staff',10),('cast',8)]:
            with self.subTest(role=role):
                cache.clear();u=get_user_model().objects.create_user('recovery-'+role,email=role+'@example.com',password=self.initial)
                UserProfile.objects.create(user=u,store=self.store,role=role)
                link=self.link(u);self.assertEqual(self.client.post('/api/auth/password-reset/validate/',link,format='json').data['min_length'],length)
                self.assertEqual(self.confirm(link).status_code,200)
                self.user.refresh_from_db();self.assertTrue(self.user.check_password(self.initial));self.assertTrue(self.user.is_superuser)

    def test_expired_token_rejected_but_30_minute_boundary_is_valid(self):
        now=datetime(2026,11,19,1)
        with patch('django.contrib.auth.tokens.PasswordResetTokenGenerator._now',return_value=now):link=self.link()
        with patch('django.contrib.auth.tokens.PasswordResetTokenGenerator._now',return_value=now+timedelta(seconds=1800)):
            self.assertEqual(self.client.post('/api/auth/password-reset/validate/',link,format='json').status_code,200)
        with patch('django.contrib.auth.tokens.PasswordResetTokenGenerator._now',return_value=now+timedelta(seconds=1801)):
            self.assertEqual(self.confirm(link).status_code,400)
        self.user.refresh_from_db();self.assertTrue(self.user.check_password(self.initial))

    def test_tampered_cross_account_disabled_and_changed_email_links_rejected(self):
        other=get_user_model().objects.create_user('another',email='another@example.com',password=self.initial)
        link=self.link()
        cases=[{**link,'token':link['token']+'x'},{**link,'uid':self.link(other)['uid']},{**link,'uid':'!invalid'}]
        for value in cases:self.assertEqual(self.confirm(value).status_code,400)
        self.user.email='changed@example.com';self.user.save(update_fields=['email']);self.assertEqual(self.confirm(link).status_code,400)
        link=self.link();self.user.is_active=False;self.user.save(update_fields=['is_active']);self.assertEqual(self.confirm(link).status_code,400)

    def test_invalid_payloads_and_mismatching_passwords_never_change_password(self):
        for body in [[],{'username':[]},{'username':'x'*151}]:
            self.assertEqual(self.client.post('/api/auth/password-reset/',body,format='json').status_code,400)
        for body in [[],{'uid':[]},{'uid':'x'*65,'token':'x'},{**self.link(),'new_password':self.changed,'new_password_confirm':'different'}]:
            self.assertEqual(self.client.post('/api/auth/password-reset/confirm/',body,format='json').status_code,400)
        self.user.refresh_from_db();self.assertTrue(self.user.check_password(self.initial))

    def test_request_and_confirm_require_csrf_handshake(self):
        client=APIClient(enforce_csrf_checks=True)
        self.assertEqual(client.post('/api/auth/password-reset/',{'username':self.user.username},format='json').status_code,403)
        client.get('/api/auth/csrf/');csrf=client.cookies['csrftoken'].value
        self.assertEqual(client.post('/api/auth/password-reset/',{'username':self.user.username},format='json',HTTP_X_CSRFTOKEN=csrf).status_code,200)
        link=self.link()
        self.assertEqual(self.confirm(link,client=client).status_code,403)
        body={**link,'new_password':self.changed,'new_password_confirm':self.changed}
        self.assertEqual(client.post('/api/auth/password-reset/confirm/',body,format='json',HTTP_X_CSRFTOKEN=csrf).status_code,200)
