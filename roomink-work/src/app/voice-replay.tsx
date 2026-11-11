import { useEffect, useRef, useState } from 'react';
import { Link } from 'expo-router';
import Constants from 'expo-constants';
import { Button, ScrollView, Text, TextInput } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { VoiceControls } from '../components/VoiceControls';
import type { VoiceRegistrationState } from '../lib/voice';
import { replayVoiceEvents } from '../lib/voice-replay.mjs';
import { createVoiceSession } from '../lib/voice-session';
import { createReplaySdk } from '../lib/voice-replay-sdk.mjs';

type DeviceEvent = { device: string; stage: string; at_ms: number; snapshot: Record<string, unknown> };
type Replay = { version: number; clock: string; device_events: DeviceEvent[] };

export default function VoiceReplay() {
  const [source, setSource] = useState('');
  const [replay, setReplay] = useState<Replay | null>(null);
  const [device, setDevice] = useState('');
  const [state, setState] = useState<VoiceRegistrationState | null>(null);
  const [timeline, setTimeline] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [running, setRunning] = useState(false);
  const generation = useRef(0);
  useEffect(() => () => { generation.current += 1; }, []);
  // This route is only available to staging / internal development builds.
  const available = Constants.expoConfig?.extra?.workBuildChannel === '検証版';
  const devices = [...new Set(replay?.device_events.map(event => event.device) ?? [])];
  const simulatedOperations = {
    accept: async () => { setTimeline(previous => [...previous, '検証操作・応答']); },
    reject: async () => { setTimeline(previous => [...previous, '検証操作・拒否']); },
    end: async () => { setTimeline(previous => [...previous, '検証操作・終了']); },
  };
  function load() {
    try {
      if (source.length > 500000) throw new Error('検証データが大きすぎます。');
      const data = JSON.parse(source) as Replay;
      if (data.version !== 1 || data.clock !== 'server_observed' ||
          !Array.isArray(data.device_events) || data.device_events.length > 500) {
        throw new Error('対応していない検証データです。');
      }
      for (const event of data.device_events) {
        if (typeof event.device !== 'string' || typeof event.stage !== 'string' ||
            !Number.isSafeInteger(event.at_ms) || Math.abs(event.at_ms) > 3600000) {
          throw new Error('端末の記録を読み取れません。');
        }
      }
      setReplay(data); setDevice(data.device_events[0]?.device ?? ''); setError('');
    } catch (reason) { setError(reason instanceof Error ? reason.message : '読み込めませんでした。'); }
  }
  async function run() {
    if (!replay || !device || running) return;
    const current = ++generation.current;
    setRunning(true); setState(null); setTimeline([]); setError('');
    const events = replay.device_events.filter(event => event.device === device).sort((left, right) => {
      const a = left.snapshot?.sequence;
      const b = right.snapshot?.sequence;
      return typeof a === 'number' && typeof b === 'number' ? a - b : left.at_ms - right.at_ms;
    });
    const useUptime = events.every(event => typeof event.snapshot?.uptime_ms === 'number');
    const eventTime = (event: DeviceEvent) => useUptime ? Number(event.snapshot.uptime_ms) : event.at_ms;
    const origin = events.length ? eventTime(events[0]) : 0;
    const transport = createReplaySdk();
    const session = createVoiceSession({
      platform: 'ios',
      loadSdk: async () => transport.sdk as unknown as typeof import('@twilio/voice-react-native-sdk'),
      record: () => {},
    });
    try {
      await session.registerForIncomingCalls('replay', next => {
        if (generation.current === current) setState(next);
      });
      await replayVoiceEvents({
        version: 1, clock: 'server_observed',
        events: events.map(event => ({ ...event, at_ms: eventTime(event) - origin, leg: device })),
      }, async (event: DeviceEvent) => {
        if (generation.current !== current) throw new Error('再生を停止しました。');
        setTimeline(previous => [...previous, JSON.stringify(event)]);
        await transport.deliver(event);
      }, async (ms: number) => {
        // Check cancellation every 100ms even when recorded events are far apart.
        for (let remaining = ms; remaining > 0; remaining -= 100) {
          if (generation.current !== current) throw new Error('再生を停止しました。');
          await new Promise(resolve => setTimeout(resolve, Math.min(100, remaining)));
        }
      });
    } catch (reason) {
      if (generation.current === current) setError(reason instanceof Error ? reason.message : '再生に失敗しました。');
    } finally {
      await session.unregisterIncomingCalls();
      if (generation.current === current) setRunning(false);
    }
  }
  return <SafeAreaView style={{ flex: 1, backgroundColor: '#fff' }}>
    <ScrollView contentContainerStyle={{ padding: 20, gap: 16 }}>
      <Link href="/">戻る</Link>
      <Text style={{ fontSize: 24 }}>着信の再生</Text>
      {!available ? <Text>検証版で利用できます。</Text> : <>
        <Text>運用画面から保存したJSONで、端末イベントの順序と時間差を再生します。iOSのPush配信・実際の着信音は実着信で確認します。</Text>
        <TextInput accessibilityLabel="検証データJSON" multiline value={source} onChangeText={setSource}
          editable={!running} style={{ minHeight: 140, borderWidth: 1, padding: 12 }} />
        <Button title="読み込む" onPress={load} disabled={running} />
        {devices.map(value => <Button key={value} title={value + (device === value ? ' ✓' : '')}
          disabled={running} onPress={() => setDevice(value)} />)}
        {replay && !devices.length && <Text>この通話には端末の記録がありません。</Text>}
        <Button title="記録どおりに再生" disabled={!device || running} onPress={() => { void run(); }} />
        {running && <Button title="停止" onPress={() => { generation.current += 1; setRunning(false); }} />}
        <Text accessibilityLiveRegion="polite">{state?.kind ?? ''}</Text>
        {state?.kind === 'error' && <Text>{state.message}</Text>}
        <VoiceControls state={state} operations={simulatedOperations} />
        {timeline.map((line, index) => <Text key={index} selectable>{line}</Text>)}
      </>}
      {!!error && <Text accessibilityRole="alert">{error}</Text>}
    </ScrollView>
  </SafeAreaView>;
}
