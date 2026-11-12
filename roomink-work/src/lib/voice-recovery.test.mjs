import assert from 'node:assert/strict';
import test from 'node:test';
import { EventEmitter } from 'node:events';
import { createVoiceSession } from './voice-session.ts';
import { readNativeVoiceState } from './native-voice-state.ts';

const flush = () => new Promise(resolve => setImmediate(resolve));
function fixture() {
  const invites = new Map(), calls = new Map(), rejected = [], states = [], records = [];
  let voice, snapshotHook, startupSnapshot, reads = 0, wrappers = 0;
  class Call extends EventEmitter {
    constructor(sid) { super(); this.sid = sid; this.state = 'connected'; }
    getSid() { return this.sid; }
    getFrom() { return ''; }
    getState() { return this.state; }
    async disconnect() { calls.delete(this.sid); this.state = 'disconnected'; this.emit('disconnected'); }
    static State = { Connected: 'connected' };
    static Event = { Connected: 'connected', Reconnected: 'reconnected', Reconnecting: 'reconnecting', Disconnected: 'disconnected', ConnectFailure: 'failure' };
  }
  class Invite extends EventEmitter {
    state = 'pending';
    constructor(sid) { super(); this.sid = sid; }
    getCallSid() { return this.sid; }
    getFrom() { return ''; }
    getState() { return this.state; }
    async reject() { rejected.push(this.sid); invites.delete(this.sid); this.state = 'rejected'; this.emit('rejected'); }
    async accept() { invites.delete(this.sid); const call = new Call(this.sid); calls.set(this.sid, call); this.state = 'accepted'; this.emit('accepted', call); return call; }
    static Event = { Accepted: 'accepted', Cancelled: 'cancelled', Rejected: 'rejected' };
  }
  class Voice extends EventEmitter {
    constructor() { super(); voice = this; }
    async register() {}
    async unregister() {}
    async getCalls() { wrappers++; return new Map(calls); }
    async getCallInvites() { wrappers++; return startupSnapshot ?? new Map(invites); }
    static Event = { CallInvite: 'invite', Error: 'error' };
  }
  const session = createVoiceSession({ platform: 'ios', loadSdk: async () => ({ Voice, Call, CallInvite: Invite }),
    record: (...args) => records.push(args), readNativeState: async () => {
      reads++;
      const state = { calls: [...calls.keys()], invites: [...invites.keys()] };
      await snapshotHook?.(reads);
      return state;
    } });
  return { session, invites, calls, states, rejected, records,
    get wrappers() { return wrappers; },
    set hook(value) { snapshotHook = value; },
    set startupSnapshot(value) { startupSnapshot = value; },
    async start() { await session.registerForIncomingCalls('fake', state => states.push(state)); },
    ring(sid) { const invite = new Invite(sid); invites.set(sid, invite); voice.emit('invite', invite); return invite; },
    last() { return states.at(-1); },
    cancel(invite, notify = true) { invites.delete(invite.sid); invite.state = 'cancelled'; if (notify) invite.emit('cancelled'); },
  };
}

test('foreground reconciliation removes ended controls without a cancellation event', async () => {
  const f = fixture(); await f.start(); const old = f.ring('old');
  f.cancel(old, false);
  await f.session.synchronizeIncomingCalls();
  assert.equal(f.last().kind, 'registered');
  f.ring('next'); assert.equal(f.last().callSid, 'next');
  assert.deepEqual(f.rejected, []);
});

test('a new invite recovers a stale pending object before the busy guard', async () => {
  const f = fixture(); await f.start(); const old = f.ring('old');
  f.invites.delete('old'); // Native ended; even the SDK object missed its event.
  f.ring('next'); await flush();
  assert.equal(f.last().callSid, 'next');
  assert.deepEqual(f.rejected, []);
  old.emit('cancelled'); assert.equal(f.last().callSid, 'next');
});

test('an actual pending invite still protects against a second simultaneous invite', async () => {
  const f = fixture(); await f.start(); f.ring('first'); f.ring('second'); await flush();
  assert.deepEqual(f.rejected, ['second']);
  assert.equal(f.last().callSid, 'first');
});

test('an active call is preserved and rejects only the new invite', async () => {
  const f = fixture(); await f.start(); f.ring('first'); await f.session.acceptIncomingCall();
  const call = f.calls.get('first');
  f.ring('second'); await flush();
  assert.equal(f.last().kind, 'connected'); assert.equal(f.last().callSid, 'first');
  assert.deepEqual(f.rejected, ['second']); assert.equal(call.state, 'connected');
});

test('missed disconnect does not leave a stale active call blocking reception', async () => {
  const f = fixture(); await f.start(); f.ring('first'); await f.session.acceptIncomingCall();
  f.calls.delete('first'); f.ring('next'); await flush();
  assert.equal(f.last().callSid, 'next'); assert.deepEqual(f.rejected, []);
});

test('a startup snapshot ending before JS restoration is not shown or answered', async () => {
  const f = fixture(); f.startupSnapshot = new Map([['old', { getCallSid: () => 'old', on() {}, getState: () => 'pending' }]]);
  await f.start(); assert.equal(f.last().kind, 'registered');
  await f.session.acceptIncomingCall();
  assert.equal(f.states.some(state => state.callSid === 'old'), false);
});

test('a new native event invalidates an in-flight snapshot of the previous invite', async () => {
  const f = fixture(); await f.start(); const old = f.ring('old');
  let ran = false;
  f.hook = () => { if (!ran) { ran = true; f.cancel(old); f.ring('next'); } };
  await f.session.synchronizeIncomingCalls(); await flush();
  assert.equal(f.last().callSid, 'next'); assert.deepEqual(f.rejected, []);
});

test('a snapshot ending mid-read is confirmed again before being adopted', async () => {
  const f = fixture(); await f.start(); f.ring('old');
  let ran = false;
  f.hook = () => { if (!ran) { ran = true; f.invites.delete('old'); } };
  await f.session.synchronizeIncomingCalls();
  assert.equal(f.last().kind, 'registered');
});

test('failed observation does not clear valid controls or disconnect a call', async () => {
  const f = fixture(); await f.start(); f.ring('first'); await f.session.acceptIncomingCall();
  f.hook = () => { throw new Error('native unavailable'); };
  await f.session.synchronizeIncomingCalls();
  assert.equal(f.last().kind, 'connected'); assert.equal(f.calls.size, 1);
});

test('logout invalidates an in-flight snapshot and does not restore old controls', async () => {
  const f = fixture(); await f.start(); f.ring('old');
  let release, entered;
  const started = new Promise(resolve => { entered = resolve; });
  f.hook = async () => { entered(); await new Promise(resolve => { release = resolve; }); };
  const sync = f.session.synchronizeIncomingCalls(); await started;
  await f.session.unregisterIncomingCalls();
  const length = f.states.length; release(); await sync;
  assert.equal(f.states.length, length);
});

test('periodic observations do not construct SDK objects or add their native listeners', async () => {
  const f = fixture(); await f.start(); f.ring('first'); const baseline = f.wrappers;
  for (let i = 0; i < 20; i++) await f.session.synchronizeIncomingCalls();
  assert.equal(f.wrappers, baseline); assert.equal(f.last().callSid, 'first');
});

test('native state reader validates responses without creating SDK wrappers', async () => {
  const result = await readNativeVoiceState({ voiceState: async () => ({ calls: ['call'], invites: ['invite'] }) });
  assert.deepEqual(result, { calls: ['call'], invites: ['invite'] });
  for (const state of [null, {}, { calls: [{}], invites: [] }, { calls: [], invites: [''] }]) {
    await assert.rejects(readNativeVoiceState({ voiceState: async () => state }));
  }
});
