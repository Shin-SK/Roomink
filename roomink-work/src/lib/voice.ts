import { Platform } from 'react-native';
import type { Call, CallInvite, Voice } from '@twilio/voice-react-native-sdk';

export type VoiceRegistrationState =
  | { kind: 'unsupported' | 'registering' | 'registered' }
  | { kind: 'invite' | 'connecting' | 'connected' | 'reconnecting'; callSid: string; from: string }
  | { kind: 'error'; message: string };

let voice: Voice | null = null;
let activeToken: string | null = null;
let pendingInvite: CallInvite | null = null;
let activeCall: Call | null = null;
let notifyCurrent: ((state: VoiceRegistrationState) => void) | null = null;
let registrationQueue: Promise<void> = Promise.resolve();

function reportError(reason: unknown) {
  notifyCurrent?.({ kind: 'error', message: reason instanceof Error ? reason.message : '通話に接続できませんでした。' });
}

function attachCall(call: Call, sdk: typeof import('@twilio/voice-react-native-sdk')) {
  if (activeCall === call) return;
  activeCall = call;
  pendingInvite = null;
  const report = (kind: 'connecting' | 'connected' | 'reconnecting') => {
    if (activeCall === call) notifyCurrent?.({ kind, callSid: call.getSid() || '', from: call.getFrom() || '' });
  };
  const finish = (error?: Error) => {
    if (activeCall !== call) return;
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

export async function registerForIncomingCalls(accessToken: string, notify: (state: VoiceRegistrationState) => void) {
  if (Platform.OS !== 'ios' && Platform.OS !== 'android') { notify({ kind: 'unsupported' }); return; }
  notifyCurrent = notify;
  const operation = registrationQueue.then(async () => {
    try {
      const sdk = await import('@twilio/voice-react-native-sdk');
      if (!voice) {
        voice = new sdk.Voice();
        voice.on(sdk.Voice.Event.CallInvite, (invite: CallInvite) => {
          if (activeCall || pendingInvite) { void invite.reject().catch(reportError); return; }
          pendingInvite = invite;
          notifyCurrent?.({ kind: 'invite', callSid: invite.getCallSid(), from: invite.getFrom() });
          invite.on(sdk.CallInvite.Event.Accepted, (call) => attachCall(call, sdk));
          const settle = () => {
            if (pendingInvite === invite) { pendingInvite = null; notifyCurrent?.({ kind: 'registered' }); }
          };
          invite.on(sdk.CallInvite.Event.Cancelled, settle);
          invite.on(sdk.CallInvite.Event.Rejected, settle);
        });
        voice.on(sdk.Voice.Event.Error, reportError);
        if (Platform.OS === 'ios') await voice.initializePushRegistry();
      }
      if (!activeCall && !pendingInvite) notifyCurrent?.({ kind: 'registering' });
      if (activeToken !== accessToken) await voice.register(accessToken);
      activeToken = accessToken;
      if (!activeCall && !pendingInvite) notifyCurrent?.({ kind: 'registered' });
    } catch (reason) { reportError(reason); }
  });
  registrationQueue = operation.catch(() => {});
  await operation;
}

export async function acceptIncomingCall() {
  const invite = pendingInvite;
  if (!invite) return;
  try {
    const sdk = await import('@twilio/voice-react-native-sdk');
    attachCall(await invite.accept(), sdk);
  } catch (reason) { reportError(reason); }
}
export async function rejectIncomingCall() {
  try { await pendingInvite?.reject(); } catch (reason) { reportError(reason); }
}
export async function endIncomingCall() {
  try { await activeCall?.disconnect(); } catch (reason) { reportError(reason); }
}
export async function unregisterIncomingCalls() {
  await registrationQueue;
  if (pendingInvite) await pendingInvite.reject();
  if (activeCall) await activeCall.disconnect();
  if (voice && activeToken) await voice.unregister(activeToken);
  activeToken = null;
  pendingInvite = null;
  activeCall = null;
  notifyCurrent = null;
}
