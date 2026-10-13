import assert from 'node:assert/strict';
import test from 'node:test';
import { applyCallSignal, mockAnswer, ringableCalls } from './incoming.ts';

const ring = (id, storeId, revision = 1) => ({ kind: 'ring', call: { id, storeId, storeName: `店舗${storeId}`, caller: 'お客さま', phone: '09000000000', revision } });

test('only entitled, receiving stores ring on an active device', () => {
  const book = applyCallSignal(applyCallSignal(applyCallSignal({}, ring('a', 1)), ring('b', 2)), ring('c', 3));
  assert.deepEqual(ringableCalls(book, [1], true).map((call) => call.id), ['a']);
  assert.deepEqual(ringableCalls(book, [2], true).map((call) => call.id), ['b']);
  assert.deepEqual(ringableCalls(book, [1, 2, 3], false), []);
  assert.deepEqual(ringableCalls(book, [], true), []);
});

test('first answer stops only its own call and later answers cannot steal it', () => {
  let book = applyCallSignal(applyCallSignal({}, ring('a', 1)), ring('b', 2));
  const first = mockAnswer(book, 'a', 'device-one');
  assert.equal(first.accepted, true);
  book = first.book;
  assert.equal(mockAnswer(book, 'a', 'device-two').accepted, false);
  assert.equal(book.a.answeredBy, 'device-one');
  assert.deepEqual(ringableCalls(book, [1, 2], true).map((call) => call.id), ['b']);
});

test('duplicate and delayed ringing cannot reopen an answered call', () => {
  let book = applyCallSignal({}, ring('a', 1));
  book = applyCallSignal(book, { kind: 'answered', callId: 'a', storeId: 1, revision: 2, deviceId: 'device-one' });
  assert.equal(applyCallSignal(book, ring('a', 1, 1)), book);
  assert.equal(applyCallSignal(book, ring('a', 1, 3)), book);
  assert.equal(book.a.status, 'answered');
});

test('an end arriving before a ring leaves a tombstone', () => {
  const book = applyCallSignal({}, { kind: 'ended', callId: 'a', storeId: 1, revision: 2 });
  assert.equal(applyCallSignal(book, ring('a', 1, 1)), book);
  assert.deepEqual(ringableCalls(book, [1], true), []);
});

test('one call ID cannot be reassigned to another store', () => {
  const book = applyCallSignal({}, ring('a', 1));
  assert.equal(applyCallSignal(book, ring('a', 2, 2)), book);
});

test('missed call closes only itself and stale events are ignored', () => {
  let book = applyCallSignal(applyCallSignal({}, ring('a', 1)), ring('b', 1));
  book = applyCallSignal(book, { kind: 'missed', callId: 'a', storeId: 1, revision: 2 });
  assert.deepEqual(ringableCalls(book, [1], true).map((call) => call.id), ['b']);
  assert.equal(applyCallSignal(book, ring('a', 1, 1)), book);
});

test('an answered call cannot later be marked missed', () => {
  let book = applyCallSignal({}, ring('a', 1));
  book = mockAnswer(book, 'a', 'device-one').book;
  assert.equal(applyCallSignal(book, { kind: 'missed', callId: 'a', storeId: 1, revision: 3 }), book);
});
