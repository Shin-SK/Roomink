import { useMemo, useState } from 'react';
import { Link } from 'expo-router';
import { ActivityIndicator, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View } from 'react-native';
import { callList } from '../lib/call-list';
import type { Device, Store, WorkCall } from '../lib/roomink';

type Props = {
  device: Device;
  calls: WorkCall[];
  history: WorkCall[];
  busy: boolean;
  error: string | null;
  onRefresh: () => void;
  onToggleStore: (store: Store) => void;
  onLogout?: () => void;
  preview?: boolean;
};

const ink = '#183733';
const green = '#197c6e';
const muted = '#62736e';
const red = '#aa4633';

function statusLabel(status: string) {
  switch (status) {
    case 'NEW': return '未対応';
    case 'IN_PROGRESS': return '対応中';
    case 'MISSED': return '不在';
    case 'DONE': return '完了';
    default: return status;
  }
}

function callTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('ja-JP', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function attention(call: WorkCall) {
  const flag = call.customer_attention?.flag;
  if (!flag || flag === 'NONE') return null;
  const label = flag === 'BAN' ? '出禁' : '要注意';
  return call.customer_attention?.staff_memo ? `${label}・${call.customer_attention.staff_memo}` : label;
}

export function CallListScreen({ device, calls, history, busy, error, onRefresh, onToggleStore, onLogout, preview = false }: Props) {
  const [section, setSection] = useState<'calls' | 'settings'>('calls');
  const [missedOnly, setMissedOnly] = useState(false);
  const [selectedStore, setSelectedStore] = useState<number | null>(null);
  const [showStoreFilter, setShowStoreFilter] = useState(false);
  const [selectedCall, setSelectedCall] = useState<number | null>(null);
  const rows = useMemo(() => callList(device, calls, history, selectedStore, missedOnly), [device, calls, history, selectedStore, missedOnly]);
  const detail = rows.find((row) => row.id === selectedCall);
  const receivingCount = device.stores.filter((store) => store.is_receiving && store.is_entitled !== false).length;

  return <SafeAreaView style={styles.safe}>
    <View style={styles.header}>
      <Text style={styles.kicker}>ROOMINK WORK</Text>
      <View style={styles.headingRow}>
        <Text style={styles.title}>{section === 'settings' ? '設定' : detail ? '通話の詳細' : '通話'}</Text>
        {section === 'calls' ? <Pressable onPress={detail ? () => setSelectedCall(null) : onRefresh} disabled={busy} style={styles.headerAction}><Text style={styles.actionText}>{detail ? '戻る' : busy ? '更新中' : '更新'}</Text></Pressable> : null}
      </View>
    </View>
    <ScrollView contentContainerStyle={styles.content}>
      {preview ? <Text style={styles.preview}>画面プレビュー · 架空の通話です。実際の電話は鳴りません。</Text> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {section === 'settings' ? <>
        <View style={styles.deviceRow}><View><Text style={styles.deviceName}>{device.label}</Text><Text style={styles.deviceStatus}>{device.status === 'active' ? `${receivingCount}店舗で受付中` : '受付停止中'}</Text></View></View>
        <Text style={styles.groupTitle}>着信を受ける店舗</Text>
        <Text style={styles.description}>休みにした店舗の新しい着信は、この端末に表示しません。履歴は残ります。</Text>
        <View style={styles.group}>{device.stores.filter((store) => store.is_entitled !== false).map((store) => <Pressable key={store.id} onPress={() => onToggleStore(store)} disabled={busy} style={styles.settingRow}>
          <View style={styles.grow}><Text style={styles.name}>{store.name}</Text><Text style={styles.secondary}>{store.is_receiving ? '受付中' : '休み'}</Text></View>
          <Text style={[styles.settingAction, !store.is_receiving && styles.paused]}>{store.is_receiving ? '休みにする' : '受付を再開'}</Text>
        </Pressable>)}</View>
        {busy ? <ActivityIndicator color={green} /> : null}
        <Text style={styles.description}>発信・ダイヤルパッドはありません。折り返しは店舗の受付回線から行ってください。</Text>
        {__DEV__ ? <Link href="/lab" style={styles.developerLink}>開発用の模擬着信テスト</Link> : null}
        {onLogout ? <Pressable onPress={onLogout} style={styles.logout}><Text style={styles.secondary}>この端末からログアウト</Text></Pressable> : null}
      </> : detail ? <>
        <View style={styles.detailHero}><Text style={[styles.detailName, detail.status === 'MISSED' && styles.missed]}>{detail.customer_name || '新規のお客さま'}</Text><Text style={styles.detailPhone}>{detail.from_phone}</Text></View>
        <View style={styles.group}>
          <View style={styles.detailRow}><Text style={styles.secondary}>店舗</Text><Text style={styles.value}>{detail.store_name}</Text></View>
          <View style={styles.detailRow}><Text style={styles.secondary}>状態</Text><Text style={styles.value}>{statusLabel(detail.status)}</Text></View>
          <View style={styles.detailRow}><Text style={styles.secondary}>日時</Text><Text style={styles.value}>{callTime(detail.created_at)}</Text></View>
        </View>
        {attention(detail) ? <Text style={styles.attention}>{attention(detail)}</Text> : null}
        <Text style={styles.description}>この画面からの発信はできません。折り返しは店舗の受付回線から行ってください。</Text>
      </> : <>
        <View style={styles.segment}><Pressable onPress={() => setMissedOnly(false)} style={[styles.segmentButton, !missedOnly && styles.segmentActive]}><Text style={[styles.segmentText, !missedOnly && styles.segmentTextActive]}>すべて</Text></Pressable><Pressable onPress={() => setMissedOnly(true)} style={[styles.segmentButton, missedOnly && styles.segmentActive]}><Text style={[styles.segmentText, missedOnly && styles.segmentTextActive]}>不在</Text></Pressable></View>
        {device.stores.length > 1 ? <><Pressable onPress={() => setShowStoreFilter((value) => !value)} style={styles.filterTrigger}><Text style={styles.filterText}>{selectedStore === null ? 'すべての店舗' : device.stores.find((store) => store.id === selectedStore)?.name || 'すべての店舗'} ▾</Text></Pressable>
          {showStoreFilter ? <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filters}><Pressable onPress={() => { setSelectedStore(null); setShowStoreFilter(false); }} style={styles.filterPill}><Text style={styles.filterText}>すべて</Text></Pressable>{device.stores.filter((store) => store.is_entitled !== false).map((store) => <Pressable key={store.id} onPress={() => { setSelectedStore(store.id); setShowStoreFilter(false); }} style={styles.filterPill}><Text style={styles.filterText}>{store.name}</Text></Pressable>)}</ScrollView> : null}
        </> : null}
        {rows.length ? <View style={styles.group}>{rows.map((call) => <Pressable key={call.id} onPress={() => setSelectedCall(call.id)} style={styles.callRow}>
          <View style={styles.grow}><Text style={[styles.name, call.status === 'MISSED' && styles.missed]} numberOfLines={1}>{call.customer_name || '新規のお客さま'}</Text><Text style={styles.secondary} numberOfLines={1}>{call.store_name} · {statusLabel(call.status)}{attention(call) ? ' · 要注意' : ''}</Text></View>
          <View style={styles.rowEnd}><Text style={styles.time}>{callTime(call.created_at)}</Text><Text style={styles.chevron}>›</Text></View>
        </Pressable>)}</View> : <Text style={styles.empty}>{missedOnly ? '不在着信はありません' : '通話はまだありません'}</Text>}
      </>}
    </ScrollView>
    <View style={styles.tabBar}><Pressable onPress={() => { setSection('calls'); setSelectedCall(null); }} style={[styles.tab, section === 'calls' && styles.tabActive]}><Text style={[styles.tabText, section === 'calls' && styles.tabTextActive]}>通話</Text></Pressable><Pressable onPress={() => { setSection('settings'); setSelectedCall(null); }} style={[styles.tab, section === 'settings' && styles.tabActive]}><Text style={[styles.tabText, section === 'settings' && styles.tabTextActive]}>設定</Text></Pressable></View>
  </SafeAreaView>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#f6faf9' }, header: { paddingHorizontal: 20, paddingTop: 14, paddingBottom: 12 }, kicker: { color: green, fontSize: 11, fontWeight: '800', letterSpacing: 1.3 },
  headingRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 4 }, title: { color: ink, fontSize: 31, fontWeight: '800' }, headerAction: { padding: 10 }, actionText: { color: green, fontWeight: '800' },
  content: { paddingHorizontal: 20, paddingBottom: 28, gap: 12 }, preview: { color: red, backgroundColor: '#fff1ea', borderRadius: 9, padding: 10, fontSize: 12 }, error: { color: red, backgroundColor: '#fff1ea', borderRadius: 9, padding: 10 },
  segment: { alignSelf: 'flex-start', flexDirection: 'row', padding: 3, borderRadius: 11, backgroundColor: '#e8efed' }, segmentButton: { paddingVertical: 8, paddingHorizontal: 17, borderRadius: 9 }, segmentActive: { backgroundColor: '#fff' }, segmentText: { color: muted, fontWeight: '700' }, segmentTextActive: { color: ink },
  filterTrigger: { alignSelf: 'flex-start', paddingVertical: 7 }, filterText: { color: green, fontWeight: '700' }, filters: { gap: 8 }, filterPill: { paddingVertical: 8, paddingHorizontal: 13, borderRadius: 20, backgroundColor: '#e8efed' },
  group: { backgroundColor: '#fff', borderRadius: 15, overflow: 'hidden' }, callRow: { minHeight: 66, paddingHorizontal: 16, paddingVertical: 12, flexDirection: 'row', alignItems: 'center', gap: 8, borderBottomColor: '#edf0ee', borderBottomWidth: 1 },
  grow: { flex: 1, minWidth: 0 }, name: { color: ink, fontSize: 17, fontWeight: '700' }, missed: { color: red }, secondary: { color: muted, fontSize: 12, marginTop: 4 }, rowEnd: { alignItems: 'flex-end', gap: 1 }, time: { color: muted, fontSize: 11 }, chevron: { color: '#9aa9a4', fontSize: 23, lineHeight: 24 },
  empty: { color: muted, backgroundColor: '#eaf4f1', padding: 20, borderRadius: 13 }, detailHero: { alignItems: 'center', paddingVertical: 24, gap: 7 }, detailName: { color: ink, fontSize: 25, fontWeight: '800' }, detailPhone: { color: muted, fontSize: 16 },
  detailRow: { flexDirection: 'row', justifyContent: 'space-between', gap: 12, padding: 15, borderBottomColor: '#edf0ee', borderBottomWidth: 1 }, value: { color: ink, fontWeight: '700', flexShrink: 1, textAlign: 'right' }, attention: { color: red, backgroundColor: '#fff1ea', padding: 13, borderRadius: 11, fontWeight: '700' },
  description: { color: muted, fontSize: 13, lineHeight: 20 }, deviceRow: { backgroundColor: ink, borderRadius: 14, padding: 18 }, deviceName: { color: '#fff', fontSize: 17, fontWeight: '800' }, deviceStatus: { color: '#cae7df', fontSize: 12, marginTop: 6 }, groupTitle: { color: ink, fontSize: 17, fontWeight: '800', marginTop: 8 },
  settingRow: { padding: 16, flexDirection: 'row', alignItems: 'center', gap: 8, borderBottomColor: '#edf0ee', borderBottomWidth: 1 }, settingAction: { color: green, fontSize: 12, fontWeight: '800' }, paused: { color: red },
  developerLink: { alignSelf: 'center', padding: 12, color: green, fontWeight: '700' }, logout: { alignSelf: 'center', padding: 15 }, tabBar: { flexDirection: 'row', padding: 8, gap: 6, borderTopColor: '#e1e9e5', borderTopWidth: 1, backgroundColor: '#fff' },
  tab: { flex: 1, alignItems: 'center', paddingVertical: 12, borderRadius: 11 }, tabActive: { backgroundColor: '#eaf4f1' }, tabText: { color: muted, fontWeight: '700' }, tabTextActive: { color: green, fontWeight: '800' },
});
