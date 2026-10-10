import { Platform } from 'react-native';

type Invite = {
  getCallSid(): string;
  getFrom(): string;
  on(event: string, listener: (...args: unknown[]) => void): void;
};

type VoiceClient = {
  initializePushRegistry(): Promise<void>;
  register(token: string): Promise<void>;
  unregister(token: string): Promise<void>;
  on(event: string, listener: (...args: any[]) => void): void;
};

type VoiceSdk = {
  Voice: new () => VoiceClient;
  CallInvite: { Event: { Accepted: string; Rejected: string; Cancelled: string } };
};

export type VoiceRegistrationState =
  | { kind: 'unsupported' }
  | { kind: 'registering' }
  | { kind: 'registered' }
  | { kind: 'invite'; callSid: string; from: string }
  | { kind: 'error'; message: string };

let voice: VoiceClient | null = null;
let activeToken: string | null = null;
let listenersAttached = false;
let notifyCurrent: ((state: VoiceRegistrationState) => void) | null = null;

async function nativeSdk(): Promise<VoiceSdk | null> {
  if (Platform.OS !== 'ios' && Platform.OS !== 'android') return null;
  // Expo web intentionally never loads this native module.
  return (await import('@twilio/voice-react-native-sdk')) as unknown as VoiceSdk;
}

export async function registerForIncomingCalls(
  accessToken: string,
  notify: (state: VoiceRegistrationState) => void,
) {
  const sdk = await nativeSdk();
  if (!sdk) {
    notify({ kind: 'unsupported' });
    return;
  }

  notify({ kind: 'registering' });
  try {
    notifyCurrent = notify;
    voice ??= new sdk.Voice();
    if (!listenersAttached) {
      voice.on('callInvite', (invite: Invite) => {
        notifyCurrent?.({ kind: 'invite', callSid: invite.getCallSid(), from: invite.getFrom() });
        invite.on(sdk.CallInvite.Event.Accepted, () => notifyCurrent?.({ kind: 'registered' }));
        invite.on(sdk.CallInvite.Event.Rejected, () => notifyCurrent?.({ kind: 'registered' }));
        invite.on(sdk.CallInvite.Event.Cancelled, () => notifyCurrent?.({ kind: 'registered' }));
      });
      voice.on('error', (error: { message?: string }) => {
        notifyCurrent?.({ kind: 'error', message: error.message || '着信機能でエラーが発生しました。' });
      });
      listenersAttached = true;
    }
    if (Platform.OS === 'ios') await voice.initializePushRegistry();
    if (activeToken !== accessToken) await voice.register(accessToken);
    activeToken = accessToken;
    notify({ kind: 'registered' });
  } catch (reason) {
    notify({ kind: 'error', message: reason instanceof Error ? reason.message : 'PushKit の登録に失敗しました。' });
  }
}

export async function unregisterIncomingCalls() {
  if (voice && activeToken) await voice.unregister(activeToken);
  activeToken = null;
  notifyCurrent = null;
}
