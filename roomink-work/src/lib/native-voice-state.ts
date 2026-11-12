import type { NativeVoiceState } from './voice-session';

type NativeReader = { voiceState: () => Promise<unknown> };

// Use a main-queue native snapshot. SDK getCallInvites()
// creates persistent JS event listeners for every returned object; polling
// those wrappers would accumulate listeners for the same invite.
export async function readNativeVoiceState(native: NativeReader): Promise<NativeVoiceState> {
  const state = await native.voiceState();
  function ids(field: 'calls' | 'invites') {
    const result = state && typeof state === 'object' ? (state as Record<string, unknown>)[field] : null;
    if (!Array.isArray(result) || result.some(sid => typeof sid !== 'string' || !sid)) {
      throw new Error('端末の通話状態を確認できませんでした。');
    }
    return result as string[];
  }
  return { calls: ids('calls'), invites: ids('invites') };
}
