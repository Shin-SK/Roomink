import test from 'node:test'
import assert from 'node:assert/strict'
import { parsePasswordResetFragment, preparePasswordResetLink, takePasswordResetLink, scrubPasswordResetUrl, scrubPasswordResetBreadcrumb } from '../src/passwordResetLink.js'

test('recovery link uses fragment values and rejects missing or ambiguous secrets', () => {
  assert.deepEqual(parsePasswordResetFragment('#uid=MQ&token=one-use'), { uid: 'MQ', token: 'one-use' })
  for (const value of ['', '#uid=MQ', '#uid=MQ&token=a&token=b', '#uid=&token=a', '#uid='+ 'x'.repeat(65)+'&token=a']) {
    assert.equal(parsePasswordResetFragment(value), null)
  }
})

test('recovery secrets leave the URL before monitoring and are consumed once', () => {
  let replaced = null
  const location = { pathname: '/password-reset', search: '', hash: '#uid=MQ&token=secret' }
  const history = { state: { keep: 1 }, replaceState: (...args) => { replaced = args } }
  preparePasswordResetLink(location, history)
  assert.deepEqual(replaced, [{ keep: 1 }, '', '/password-reset'])
  assert.deepEqual(takePasswordResetLink(), { uid: 'MQ', token: 'secret' })
  assert.equal(takePasswordResetLink(), null)
})

test('ordinary routes are left intact', () => {
  preparePasswordResetLink({ pathname: '/op/schedule', hash: '#date' }, { replaceState: () => assert.fail('unexpected change') })
  assert.equal(takePasswordResetLink(), null)
})

test('recovery secrets never appear in monitoring URLs or navigation breadcrumbs', () => {
  const value='https://app.roomink.net/password-reset#uid=MQ&token=secret'
  assert.equal(scrubPasswordResetUrl(value),'https://app.roomink.net/password-reset')
  assert.equal(scrubPasswordResetUrl('#uid=MQ&token=secret'),'')
  const entry=scrubPasswordResetBreadcrumb({data:{from:value,to:value,url:value,method:'POST'}})
  assert.equal(JSON.stringify(entry).includes('secret'),false)
  assert.equal(entry.data.method,'POST')
  assert.equal(scrubPasswordResetUrl('/op/orders/42'),'/op/orders/42')
})
