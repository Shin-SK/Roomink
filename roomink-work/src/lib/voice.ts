import { Platform } from 'react-native';
import { recordVoiceDiagnostic } from './diagnostics';
import { createVoiceSession } from './voice-session';
export type { VoiceRegistrationState } from './voice-session';

const session = createVoiceSession({
  platform: Platform.OS,
  loadSdk: () => import('@twilio/voice-react-native-sdk'),
  record: recordVoiceDiagnostic,
});

export const { registerForIncomingCalls, acceptIncomingCall, rejectIncomingCall, endIncomingCall, unregisterIncomingCalls } = session;
