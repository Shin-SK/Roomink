import assert from 'node:assert/strict';
import test from 'node:test';
import { callList } from './call-list.ts';

const device = { status: 'active', stores: [
  { id: 1, name: 'A', is_receiving: true, is_entitled: true },
  { id: 2, name: 'B', is_receiving: false, is_entitled: true },
] };
const call = (id, store_id, status, created_at) => ({ id, store_id, status, created_at });

test('one chronological list includes current calls and history without duplicate rows', () => {
  const current = [call(1, 1, 'NEW', '2026-10-09T00:00:00Z'), call(2, 1, 'IN_PROGRESS', '2026-10-09T02:00:00Z')];
  const history = [call(1, 1, 'DONE', '2026-10-09T00:00:00Z'), call(3, 2, 'MISSED', '2026-10-09T01:00:00Z')];
  assert.deepEqual(callList(device, current, history, null, false).map(({ id, status }) => [id, status]), [[2, 'IN_PROGRESS'], [3, 'MISSED'], [1, 'DONE']]);
});

test('a paused store hides current calls but keeps its history', () => {
  const current = [call(1, 2, 'NEW', '2026-10-09T00:00:00Z')];
  const history = [call(2, 2, 'MISSED', '2026-10-09T01:00:00Z')];
  assert.deepEqual(callList(device, current, history, null, false).map((row) => row.id), [2]);
  assert.deepEqual(callList(device, current, history, 2, true).map((row) => row.id), [2]);
});

test('store filter and entitlement prevent cross-store rows', () => {
  const current = [call(1, 1, 'NEW', '2026-10-09T00:00:00Z'), call(2, 3, 'NEW', '2026-10-09T01:00:00Z')];
  const history = [call(3, 2, 'DONE', '2026-10-09T02:00:00Z'), call(4, 3, 'MISSED', '2026-10-09T03:00:00Z')];
  assert.deepEqual(callList(device, current, history, 1, false).map((row) => row.id), [1]);
  assert.deepEqual(callList(device, current, history, null, false).map((row) => row.id), [3, 1]);
});
