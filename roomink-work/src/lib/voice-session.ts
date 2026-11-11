import type { Call, CallInvite, Voice } from '@twilio/voice-react-native-sdk';

export type VoiceRegistrationState =
  | { kind: 'unsupported' | 'registering' | 'registered' }
  | { kind: 'invite' | 'connecting' | 'connected' | 'reconnecting'; callSid: string; from: string }
  | { kind: 'error'; message: string };


export function createVoiceSession({ platform, loadSdk, record }: {
  platform: string;
  loadSdk: () => Promise<typeof import('@twilio/voice-react-native-sdk')>;
  record: (stage: string, callSid?: string, error?: unknown) => void;
}) {
  let voice: Voice | null = null;
  let activeToken: string | null = null;
  let pendingInvite: CallInvite | null = null;
  let activeCall: Call | null = null;
  let notifyCurrent: ((state: VoiceRegistrationState) => void) | null = null;
  let registrationQueue: Promise<void> = Promise.resolve();

  function reportError(reason: unknown) {
    record('error', activeCall?.getSid() || pendingInvite?.getCallSid() || '', reason);
    notifyCurrent?.({ kind: 'error', message: reason instanceof Error ? reason.message : '通話に接続できませんでした。' });
  }

  function attachCall(call: Call, sdk: typeof import('@twilio/voice-react-native-sdk')) {
    if (activeCall === call) return;
    activeCall = call;
    pendingInvite = null;
    const report = (kind: 'connecting' | 'connected' | 'reconnecting') => {
      record(kind, call.getSid() || '');
      if (activeCall === call) notifyCurrent?.({ kind, callSid: call.getSid() || '', from: call.getFrom() || '' });
    };
    const finish = (error?: Error) => {
      if (activeCall !== call) return;
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
    const operation = registrationQueue.then(async () => {
      try {
        const sdk = await loadSdk();
        if (!voice) {
          voice = new sdk.Voice();
          const showInvite = (invite: CallInvite) => {
            if (pendingInvite?.getCallSid() === invite.getCallSid()) return;
            if (activeCall || pendingInvite) { void invite.reject().catch(reportError); return; }
            pendingInvite = invite;
            record('invite', invite.getCallSid());
            notifyCurrent?.({ kind: 'invite', callSid: invite.getCallSid(), from: invite.getFrom() });
            invite.on(sdk.CallInvite.Event.Accepted, (call) => attachCall(call, sdk));
            const settle = () => {
              if (pendingInvite === invite) { pendingInvite = null; notifyCurrent?.({ kind: 'registered' }); }
            };
            invite.on(sdk.CallInvite.Event.Cancelled, () => { record('cancelled', invite.getCallSid()); settle(); });
            invite.on(sdk.CallInvite.Event.Rejected, () => { record('rejected', invite.getCallSid()); settle(); });
          };
          voice.on(sdk.Voice.Event.CallInvite, showInvite);
          voice.on(sdk.Voice.Event.Error, reportError);
          if (platform === 'ios') {
            // CallKit may have handled the call before JavaScript began listening.
            const calls = await voice.getCalls();
            const existingCall = calls.values().next().value;
            if (!activeCall && existingCall) attachCall(existingCall, sdk);
            const invites = await voice.getCallInvites();
            if (!activeCall && !pendingInvite) {
              const existingInvite = invites.values().next().value;
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
        if (!activeCall && !pendingInvite) notifyCurrent?.({ kind: 'registered' });
      } catch (reason) { record('registration_failed', '', reason); reportError(reason); }
    });
    registrationQueue = operation.catch(() => {});
    await operation;
  }

  async function acceptIncomingCall() {
    const invite = pendingInvite;
    if (!invite) return;
    record('accepted', invite.getCallSid());
    try {
      const sdk = await loadSdk();
      attachCall(await invite.accept(), sdk);
    } catch (reason) { reportError(reason); }
  }
  async function rejectIncomingCall() {
    try { await pendingInvite?.reject(); } catch (reason) { reportError(reason); }
  }
  async function endIncomingCall() {
    try { await activeCall?.disconnect(); } catch (reason) { reportError(reason); }
  }
  async function unregisterIncomingCalls() {
    await registrationQueue;
    if (pendingInvite) await pendingInvite.reject();
    if (activeCall) await activeCall.disconnect();
    if (voice && activeToken) await voice.unregister(activeToken);
    activeToken = null;
    pendingInvite = null;
    activeCall = null;
    notifyCurrent = null;
  }
  return { registerForIncomingCalls, acceptIncomingCall, rejectIncomingCall, endIncomingCall, unregisterIncomingCalls };
}
