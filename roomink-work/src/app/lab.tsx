import { Link, Redirect } from 'expo-router';
import { useMemo, useState } from 'react';
import { Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View } from 'react-native';
import { applyCallSignal, CallBook, mockAnswer, ringableCalls } from '../lib/incoming';

const stores = [{ id: 1, name: 'Work検証 A店' }, { id: 2, name: 'Work検証 B店' }, { id: 3, name: 'Work検証 C店' }];
const devices = ['受付端末 1', '受付端末 2'];

export default function CallLab() {
  const [book, setBook] = useState<CallBook>({});
  const [sequence, setSequence] = useState(0);
  const [deviceIndex, setDeviceIndex] = useState(0);
  const [receiving, setReceiving] = useState<number[][]>([[1, 2, 3], [2]]);
  const [message, setMessage] = useState('端末を切り替えて、同じ着信がどう見えるか確認できます。');
  const current = devices[deviceIndex];
  const visible = useMemo(() => ringableCalls(book, receiving[deviceIndex], true), [book, receiving, deviceIndex]);

  if (!__DEV__) return <Redirect href="/" />;

  function addCall(storeId: number) {
    const next = sequence + 1;
    const store = stores.find((row) => row.id === storeId)!;
    setSequence(next);
    setBook((previous) => applyCallSignal(previous, { kind: 'ring', call: {
      id: `local-${next}`, storeId, storeName: store.name,
      caller: next % 2 ? '山田さま' : '新規のお客さま', phone: '090-0000-0000',
      attention: next % 2 ? '要注意：受付時に確認' : undefined, revision: 1,
    } }));
    setMessage(`${store.name}の模擬着信を追加しました。実際の電話や通知は送っていません。`);
  }

  function answer(callId: string, answeringDevice: string) {
    const result = mockAnswer(book, callId, answeringDevice);
    setBook(result.book);
    setMessage(result.accepted ? `${answeringDevice}が応答。ほかの端末では、この着信だけ止まります。` : 'すでに別の端末で応答済みです。');
  }

  function toggleReceiving(storeId: number) {
    setReceiving((previous) => previous.map((ids, index) => index !== deviceIndex ? ids : ids.includes(storeId) ? ids.filter((id) => id !== storeId) : [...ids, storeId]));
  }

  return <SafeAreaView style={styles.safe}><ScrollView contentContainerStyle={styles.page}>
    <Text style={styles.kicker}>ROOMINK WORK · LOCAL LAB</Text>
    <Text style={styles.title}>着信の動き</Text>
    <Text style={styles.intro}>フェーズ4のローカル検証用です。実際の着信・音声通話・OS通知はまだ行いません。</Text>
    <Link href="/" style={styles.back}>受付画面へ戻る</Link>
    <View style={styles.deviceSwitch}>{devices.map((name, index) => <Pressable key={name} onPress={() => setDeviceIndex(index)} style={[styles.deviceButton, index === deviceIndex && styles.activeDevice]}><Text style={[styles.deviceText, index === deviceIndex && styles.activeDeviceText]}>{name}</Text></Pressable>)}</View>
    <Text style={styles.section}>{current}の受付店舗</Text>
    {stores.map((store) => <Pressable key={store.id} onPress={() => toggleReceiving(store.id)} style={styles.storeRow}><Text style={styles.storeText}>{store.name}</Text><Text style={styles.storeState}>{receiving[deviceIndex].includes(store.id) ? '受付中' : '休み'}</Text></Pressable>)}
    <Text style={styles.section}>模擬着信を追加</Text>
    <View style={styles.actions}>{stores.map((store) => <Pressable key={store.id} onPress={() => addCall(store.id)} style={styles.outlineButton}><Text style={styles.outlineText}>{store.name}</Text></Pressable>)}</View>
    <Text style={styles.section}>この端末に見える着信</Text>
    {visible.length ? visible.map((call) => <View key={call.id} style={styles.callCard}>
      <Text style={styles.storeLabel}>{call.storeName}</Text>
      <Text style={styles.caller}>{call.caller}</Text>
      <Text style={styles.phone}>{call.phone}</Text>
      {call.attention ? <Text style={styles.attention}>{call.attention}</Text> : null}
      <View style={styles.actions}>
        <Pressable onPress={() => answer(call.id, current)} style={styles.answerButton}><Text style={styles.answerText}>この端末で応答（模擬）</Text></Pressable>
        {receiving[1 - deviceIndex].includes(call.storeId) ? <Pressable onPress={() => answer(call.id, devices[1 - deviceIndex])} style={styles.otherButton}><Text style={styles.otherText}>他端末が応答</Text></Pressable> : null}
      </View>
    </View>) : <View style={styles.empty}><Text style={styles.emptyText}>表示する着信はありません</Text></View>}
    <Text style={styles.message}>{message}</Text>
    <Text style={styles.caution}>この検証画面は開発中だけ表示されます。実機のロック中・終了中の着信や、サーバー側の応答競合は別途検証が必要です。</Text>
  </ScrollView></SafeAreaView>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#f6faf9' }, page: { padding: 20, gap: 12, paddingBottom: 36 },
  kicker: { color: '#2a9d8f', fontSize: 11, fontWeight: '900', letterSpacing: 1.4 },
  title: { color: '#183733', fontSize: 29, fontWeight: '800' }, intro: { color: '#62736e', lineHeight: 22 },
  back: { color: '#197c6e', fontWeight: '700', paddingVertical: 8 }, section: { color: '#183733', fontSize: 17, fontWeight: '800', marginTop: 12 },
  deviceSwitch: { flexDirection: 'row', backgroundColor: '#e8efed', borderRadius: 12, padding: 4, gap: 4 },
  deviceButton: { flex: 1, paddingVertical: 12, alignItems: 'center', borderRadius: 9 }, activeDevice: { backgroundColor: '#fff' },
  deviceText: { color: '#62736e', fontWeight: '700' }, activeDeviceText: { color: '#197c6e' },
  storeRow: { backgroundColor: '#fff', padding: 14, borderRadius: 12, flexDirection: 'row', justifyContent: 'space-between' },
  storeText: { color: '#183733', fontWeight: '700' }, storeState: { color: '#197c6e', fontWeight: '800' },
  actions: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' }, outlineButton: { borderColor: '#80b9ad', borderWidth: 1, borderRadius: 10, paddingVertical: 10, paddingHorizontal: 12 },
  outlineText: { color: '#197c6e', fontWeight: '800' }, callCard: { backgroundColor: '#fff', borderRadius: 16, padding: 18, gap: 6, borderLeftColor: '#2a9d8f', borderLeftWidth: 4 },
  storeLabel: { color: '#197c6e', fontWeight: '800' }, caller: { color: '#183733', fontSize: 23, fontWeight: '800' },
  phone: { color: '#62736e', fontSize: 15 }, attention: { color: '#a7472c', backgroundColor: '#fff1ea', padding: 10, borderRadius: 8, fontWeight: '700' },
  answerButton: { backgroundColor: '#197c6e', borderRadius: 10, padding: 12 }, answerText: { color: '#fff', fontWeight: '800' },
  otherButton: { backgroundColor: '#e8efed', borderRadius: 10, padding: 12 }, otherText: { color: '#183733', fontWeight: '800' },
  empty: { backgroundColor: '#eaf4f1', borderRadius: 14, padding: 20 }, emptyText: { color: '#62736e' },
  message: { color: '#183733', lineHeight: 20 }, caution: { color: '#62736e', fontSize: 12, lineHeight: 18, marginTop: 10 },
});
