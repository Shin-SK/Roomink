import type { Call, CallInvite, Voice } from '@twilio/voice-react-native-sdk';

export type VoiceRegistrationState =
  | { kind: 'unsupported' | 'registering' | 'registered' }
  | { kind: 'invite' | 'connecting' | 'connected' | 'reconnecting'; callSid: string; from: string }
  | { kind: 'error'; message: string };

export type NativeVoiceState = { calls: string[]; invites: string[] };

export function createVoiceSession({ platform, loadSdk, record, readNativeState }: {
  platform: string;
  loadSdk: () => Promise<typeof import('@twilio/voice-react-native-sdk')>;
  record: (stage: string, callSid?: string, error?: unknown) => void;
  readNativeState?: () => Promise<NativeVoiceState>;
}) {
  let voice: Voice | null = null;
  let activeToken: string | null = null;
  let pendingInvite: CallInvite | null = null;
  let activeCall: Call | null = null;
  let notifyCurrent: ((state: VoiceRegistrationState) => void) | null = null;
  let registrationQueue: Promise<void> = Promise.resolve();
  let epoch = 0;
  let revision = 0;
  let enabled = false;
  let acting = false;
  let synchronizing: Promise<void> | null = null;
  const endedInvites = new Set<string>();
  const boundInvites = new WeakSet<CallInvite>();

  function rememberEnded(sid: string) {
    endedInvites.add(sid);
    if (endedInvites.size > 256) endedInvites.delete(endedInvites.values().next().value!);
  }

  function pending(invite: CallInvite) {
    const state = invite.getState?.();
    return !endedInvites.has(invite.getCallSid()) && (!state || state === 'pending');
  }

  function settleInvite(invite: CallInvite) {
    revision++;
    rememberEnded(invite.getCallSid());
    if (pendingInvite?.getCallSid() === invite.getCallSid()) {
      pendingInvite = null;
      if (!activeCall) notifyCurrent?.({ kind: 'registered' });
    }
  }

  async function nativeState(): Promise<NativeVoiceState> {
    if (readNativeState) return readNativeState();
    const calls = await voice!.getCalls();
    const invites = await voice!.getCallInvites();
    return { calls: [...calls.values()].map(call => call.getSid() || ''),
      invites: [...invites.values()].map(invite => invite.getCallSid()) };
  }

  // Two agreeing snapshots avoid restoring an invite that ended while a
  // native response was in flight. Events invalidate an in-flight snapshot.
  async function stableState(): Promise<NativeVoiceState | null> {
    const started = epoch;
    let previous = '';
    for (let attempt = 0; attempt < 4; attempt++) {
      const version = revision;
      const state = await nativeState();
      if (started !== epoch || !enabled) return null;
      if (version !== revision) { previous = ''; continue; }
      const fingerprint = JSON.stringify([[...state.calls].sort(), [...state.invites].sort()]);
      if (previous === fingerprint) return state;
      previous = fingerprint;
    }
    return null;
  }

  async function reconcile() {
    if (!voice || !enabled || acting || platform !== 'ios') return null;
    const started = epoch;
    const version = revision;
    const state = await stableState();
    if (!state || acting || started !== epoch || version !== revision) return null;
    if (pendingInvite && (!pending(pendingInvite) || !state.invites.includes(pendingInvite.getCallSid()))) {
      const sid = pendingInvite.getCallSid();
      // An answer can move the invite into the native call map before its JS
      // Accepted event. Adopt that call instead of clearing a live session.
      if (state.calls.includes(sid)) {
        const sdk = await loadSdk();
        const current = epoch;
        const version = revision;
        const calls = await voice.getCalls();
        if (current !== epoch || version !== revision || !enabled) return null;
        const call = [...calls.values()].find(call => call.getSid() === sid);
        if (call) attachCall(call, sdk);
        return state;
      }
      record('ended', sid);
      settleInvite(pendingInvite);
    }
    // Do not infer a connecting call has ended from an absent SID.
    if (activeCall?.getSid() && !state.calls.includes(activeCall.getSid()!)) {
      record('ended', activeCall.getSid() || '');
      activeCall = null;
      revision++;
      if (!pendingInvite) notifyCurrent?.({ kind: 'registered' });
    }
    return state;
  }

  async function synchronizeIncomingCalls() {
    if (!voice || !enabled || (!pendingInvite && !activeCall)) return;
    if (synchronizing) return synchronizing;
    synchronizing = reconcile().then(() => {}, reason => {
      // A failed observation must not clear or disconnect a real call.
      record('error', pendingInvite?.getCallSid() || activeCall?.getSid() || '', reason);
    }).finally(() => { synchronizing = null; });
    await synchronizing;
  }

  function reportError(reason: unknown) {
    record('error', activeCall?.getSid() || pendingInvite?.getCallSid() || '', reason);
    notifyCurrent?.({ kind: 'error', message: reason instanceof Error ? reason.message : '通話に接続できませんでした。' });
  }

  function attachCall(call: Call, sdk: typeof import('@twilio/voice-react-native-sdk')) {
    if (activeCall === call || (call.getSid() && activeCall?.getSid() === call.getSid())) return;
    const attachedEpoch = epoch;
    revision++;
    activeCall = call;
    pendingInvite = null;
    const report = (kind: 'connecting' | 'connected' | 'reconnecting') => {
      record(kind, call.getSid() || '');
      if (attachedEpoch === epoch && activeCall === call) notifyCurrent?.({ kind, callSid: call.getSid() || '', from: call.getFrom() || '' });
    };
    const finish = (error?: Error) => {
      if (attachedEpoch !== epoch || activeCall !== call) return;
      revision++;
      record('ended', call.getSid() || '', error);
      activeCall = null;
      if (error) reportError(error);
      else notifyCurrent?.({ kind: 'registered' });
    };
    call.on(sdk.Call.Event.Connected, () => report('connected'));
    call.on(sdk.Call.Event.Reconnected, () => report('connected'));
    call.on(sdk.Call.Event.Reconnecting, () => report('reconnecting'));
    call.on(sdk.Call.Event.Disconnected, finish);
    call.on(sdk.Call.Event.ConnectFailure, finish);
    report(call.getState() === sdk.Call.State.Connected ? 'connected' : 'connecting');
  }

  async function registerForIncomingCalls(accessToken: string, notify: (state: VoiceRegistrationState) => void) {
    if (platform !== 'ios' && platform !== 'android') { notify({ kind: 'unsupported' }); return; }
    notifyCurrent = notify;
    enabled = true;
    const operation = registrationQueue.then(async () => {
      try {
        const sdk = await loadSdk();
        if (!voice) {
          voice = new sdk.Voice();
          const showInvite = (invite: CallInvite) => {
            if (!enabled || !pending(invite)) return;
            if (pendingInvite?.getCallSid() === invite.getCallSid()) return;
            if (activeCall || pendingInvite) { void invite.reject().catch(reportError); return; }
            pendingInvite = invite;
            revision++;
            record('invite', invite.getCallSid());
            notifyCurrent?.({ kind: 'invite', callSid: invite.getCallSid(), from: invite.getFrom() });
          };
          const bindInvite = (invite: CallInvite) => {
            if (boundInvites.has(invite)) return;
            boundInvites.add(invite);
            const receivedEpoch = epoch;
            invite.on(sdk.CallInvite.Event.Accepted, (call) => {
              if (receivedEpoch === epoch && enabled && !endedInvites.has(invite.getCallSid())) attachCall(call, sdk);
            });
            invite.on(sdk.CallInvite.Event.Cancelled, () => {
              if (receivedEpoch !== epoch) return;
              record('cancelled', invite.getCallSid()); settleInvite(invite);
            });
            invite.on(sdk.CallInvite.Event.Rejected, () => {
              if (receivedEpoch !== epoch) return;
              record('rejected', invite.getCallSid()); settleInvite(invite);
            });
          };
          voice.on(sdk.Voice.Event.CallInvite, (invite: CallInvite) => {
            bindInvite(invite);
            revision++;
            if (!pendingInvite && !activeCall) { showInvite(invite); return; }
            const receivedEpoch = epoch;
            // Recheck stale local state before rejecting a new real invite.
            const operation = registrationQueue.then(async () => {
              const state = await reconcile();
              if (receivedEpoch !== epoch || !enabled || !pending(invite)) return;
              if (state && !state.invites.includes(invite.getCallSid())) { settleInvite(invite); return; }
              showInvite(invite);
            }).catch(reportError);
            registrationQueue = operation;
          });
          voice.on(sdk.Voice.Event.Error, reportError);
          if (platform === 'ios') {
            // CallKit may have handled the call before JavaScript began listening.
            const calls = await voice.getCalls();
            const existingCall = calls.values().next().value;
            if (!activeCall && existingCall) attachCall(existingCall, sdk);
            const invites = await voice.getCallInvites();
            for (const invite of invites.values()) bindInvite(invite);
            const state = await stableState();
            if (!activeCall && !pendingInvite) {
              const existingInvite = [...invites.values()].find(invite => state?.invites.includes(invite.getCallSid()) && pending(invite));
              if (existingInvite) showInvite(existingInvite);
            }
          }
        }
        if (!activeCall && !pendingInvite) notifyCurrent?.({ kind: 'registering' });
        if (activeToken !== accessToken) {
          record('registering');
          await voice.register(accessToken);
          record('registered');
        }
        activeToken = accessToken;
        await reconcile();
        if (!activeCall && !pendingInvite) notifyCurrent?.({ kind: 'registered' });
      } catch (reason) { record('registration_failed', '', reason); reportError(reason); }
    });
    registrationQueue = operation.catch(() => {});
    await operation;
  }

  async function acceptIncomingCall() {
    const invite = pendingInvite;
    if (!invite) return;
    const acceptedEpoch = epoch;
    record('accepted', invite.getCallSid());
    acting = true;
    revision++;
    try {
      const sdk = await loadSdk();
      const call = await invite.accept();
      if (acceptedEpoch === epoch && enabled) attachCall(call, sdk);
      else await call.disconnect();
    } catch (reason) { reportError(reason); }
    finally { acting = false; revision++; await synchronizeIncomingCalls(); }
  }
  async function rejectIncomingCall() {
    try { await pendingInvite?.reject(); } catch (reason) { reportError(reason); }
  }
  async function endIncomingCall() {
    try { await activeCall?.disconnect(); } catch (reason) { reportError(reason); }
  }
  async function unregisterIncomingCalls() {
    enabled = false;
    epoch++;
    revision++;
    await registrationQueue;
    if (pendingInvite) await pendingInvite.reject();
    if (activeCall) await activeCall.disconnect();
    if (voice && activeToken) await voice.unregister(activeToken);
    activeToken = null;
    pendingInvite = null;
    activeCall = null;
    notifyCurrent = null;
  }
  return { registerForIncomingCalls, acceptIncomingCall, rejectIncomingCall, endIncomingCall, unregisterIncomingCalls, synchronizeIncomingCalls };
}
