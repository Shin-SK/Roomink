import { AppState, NativeModules, Platform } from 'react-native';
import { getToken, workRequest } from './roomink';

type Observation = { event_id: string; observed_at: string };
const native = Platform.OS === 'ios' ? NativeModules.RoominkDiagnostics : undefined;
let uploading = false;

export function recordVoiceDiagnostic(stage: string, callSid = '', error?: unknown) {
  const code = error && typeof error === 'object' && 'code' in error ? Number(error.code) : undefined;
  native?.record(stage, callSid, Number.isFinite(code) ? code : null);
  void flushVoiceDiagnostics();
}

export async function flushVoiceDiagnostics() {
  if (!native || uploading) return;
  const token = await getToken();
  if (!token) return;
  const base = process.env.EXPO_PUBLIC_ROOMINK_API_BASE_URL?.replace(/\/$/, '');
  if (base) native.configure(base + '/work/diagnostics/', token);
  uploading = true;
  try {
    const queue = await native.read() as Observation[];
    const fresh = queue.filter(event => Date.parse(event.observed_at) >= Date.now() - 7 * 86400000);
    const expired = queue.filter(event => !fresh.includes(event)).map(event => event.event_id);
    if (expired.length) native.acknowledge(expired);
    for (let index = 0; index < fresh.length; index += 100) {
      const result = await workRequest<{ accepted: string[] }>('/work/diagnostics/', {
        method: 'POST', body: JSON.stringify({ events: fresh.slice(index, index + 100) }),
      });
      native.acknowledge(result.accepted);
    }
  } catch {
    // Keep observations until the next foreground, registration, or periodic retry.
  } finally {
    uploading = false;
  }
}

export function clearVoiceDiagnostics() { native?.clear(); }

export function startVoiceDiagnostics() {
  void flushVoiceDiagnostics();
  const subscription = AppState.addEventListener('change', () => {
    recordVoiceDiagnostic('app_state');
  });
  const timer = setInterval(() => { void flushVoiceDiagnostics(); }, 30000);
  return () => { subscription.remove(); clearInterval(timer); };
}
