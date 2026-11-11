import assert from 'node:assert/strict';
import test from 'node:test';
import { replayVoiceEvents } from './voice-replay.mjs';
import { createVoiceSession } from './voice-session.ts';
import { createReplaySdk } from './voice-replay-sdk.mjs';

test('replays cancellation before preparation using the captured timing', async () => {
  const output = [];
  const events = [
    { at_ms: 0, leg: 'device-1', stage: 'push_received' },
    { at_ms: 40, leg: 'device-1', stage: 'cancelled' },
    { at_ms: 70, leg: 'device-1', stage: 'registered' },
  ];
  await replayVoiceEvents({ version: 1, clock: 'server_observed', events },
    event => output.push(event.stage), delay => output.push(delay));
  assert.deepEqual(output, ['push_received', 40, 'cancelled', 30, 'registered']);
});

test('validates the entire sequence before dispatching any events', async () => {
  let dispatched = 0;
  await assert.rejects(replayVoiceEvents({
    version: 1, clock: 'server_observed',
    events: [{ at_ms: 50, stage: 'invite', leg: 'device-1' }, { at_ms: 10, stage: 'ended', leg: 'device-1' }],
  }, () => { dispatched++; }, () => {}));
  assert.equal(dispatched, 0);
});

test('an interrupted replay never dispatches a later event', async () => {
  const output = [];
  await assert.rejects(replayVoiceEvents({
    version: 1, clock: 'server_observed',
    events: [{ at_ms: 0, stage: 'invite', leg: 'device-1' }, { at_ms: 1000, stage: 'ended', leg: 'device-1' }],
  }, event => output.push(event.stage), () => { throw new Error('stopped'); }));
  assert.deepEqual(output, ['invite']);
});

test('replays through the live voice session and never invokes a real transport', async () => {
  const transport = createReplaySdk();
  const states = [];
  const session = createVoiceSession({
    platform: 'ios', loadSdk: async () => transport.sdk, record: () => {},
  });
  await session.registerForIncomingCalls('fake', state => states.push(state.kind));
  await transport.deliver({ stage: 'invite' });
  await transport.deliver({ stage: 'accepted' });
  await transport.deliver({ stage: 'connected' });
  await transport.deliver({ stage: 'ended' });
  assert.deepEqual(states, ['registering', 'registered', 'invite', 'connecting', 'connected', 'registered']);
  await session.unregisterIncomingCalls();
});

test('cancelled invites use the real settlement handler and cannot be answered', async () => {
  const transport = createReplaySdk();
  const states = [];
  const session = createVoiceSession({
    platform: 'ios', loadSdk: async () => transport.sdk, record: () => {},
  });
  await session.registerForIncomingCalls('fake', state => states.push(state.kind));
  await transport.deliver({ stage: 'invite' });
  await transport.deliver({ stage: 'cancelled' });
  await session.acceptIncomingCall();
  assert.deepEqual(states, ['registering', 'registered', 'invite', 'registered']);
  await session.unregisterIncomingCalls();
});
