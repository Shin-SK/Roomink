import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { acceptIncomingCall, endIncomingCall, rejectIncomingCall, VoiceRegistrationState } from '../lib/voice';

export function VoiceControls({ state }: { state: VoiceRegistrationState | null }) {
  const [busy, setBusy] = useState(false);
  if (!state || !['invite', 'connecting', 'connected', 'reconnecting'].includes(state.kind)) return null;
  const action = async (operation: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    try { await operation(); } finally { setBusy(false); }
  };
  const label = state.kind === 'invite' ? '着信中' : state.kind === 'connected' ? '通話中' : state.kind === 'reconnecting' ? '再接続中' : '接続中';
  return <View style={styles.card} accessibilityLiveRegion="polite">
    <Text style={styles.label}>{label}</Text>
    <View style={styles.actions}>
      {state.kind === 'invite' ? <>
        <Pressable accessibilityRole="button" disabled={busy} style={styles.answer} onPress={() => { void action(acceptIncomingCall); }}><Text style={styles.text}>応答</Text></Pressable>
        <Pressable accessibilityRole="button" disabled={busy} style={styles.end} onPress={() => { void action(rejectIncomingCall); }}><Text style={styles.text}>拒否</Text></Pressable>
      </> : <Pressable accessibilityRole="button" disabled={busy} style={styles.end} onPress={() => { void action(endIncomingCall); }}><Text style={styles.text}>通話を終了</Text></Pressable>}
    </View>
  </View>;
}

const styles = StyleSheet.create({
  card: { padding: 20, backgroundColor: '#edf5f2', borderBottomWidth: 1, borderColor: '#47756f' },
  label: { color: '#183733', fontSize: 20, fontWeight: '700', marginBottom: 12 },
  actions: { flexDirection: 'row', gap: 12 },
  answer: { backgroundColor: '#47756f', padding: 16, borderRadius: 12, flex: 1, alignItems: 'center' },
  end: { backgroundColor: '#b5532e', padding: 16, borderRadius: 12, flex: 1, alignItems: 'center' },
  text: { color: 'white', fontWeight: '700', fontSize: 17 },
});
