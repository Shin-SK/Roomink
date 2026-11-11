import { NativeModules, Platform } from 'react-native';
import { recordVoiceDiagnostic } from './diagnostics';
import { createVoiceSession } from './voice-session';
import { readNativeVoiceState } from './native-voice-state';
export type { VoiceRegistrationState } from './voice-session';

const session = createVoiceSession({
  platform: Platform.OS,
  loadSdk: () => import('@twilio/voice-react-native-sdk'),
  record: recordVoiceDiagnostic,
  readNativeState: Platform.OS === 'ios' ? () => readNativeVoiceState(NativeModules.RoominkDiagnostics) : undefined,
});

export const { registerForIncomingCalls, acceptIncomingCall, rejectIncomingCall, endIncomingCall, unregisterIncomingCalls, synchronizeIncomingCalls } = session;
