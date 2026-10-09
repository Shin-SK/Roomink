import { useMemo, useState } from 'react';
import { Link } from 'expo-router';
import { ActivityIndicator, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View } from 'react-native';
import type { Device, Store, WorkCall } from '../lib/roomink';

type Tab = 'calls' | 'history' | 'stores';

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

const colors = { ink: '#183733', green: '#197c6e', mint: '#eaf4f1', paper: '#f6faf9', muted: '#62736e', warning: '#a7472c' };

function attentionText(call: WorkCall) {
  const flag = call.customer_attention?.flag;
  if (!flag || flag === 'NONE') return null;
  const label = flag === 'BAN' ? '出禁' : '要注意';
  return call.customer_attention?.staff_memo ? `${label} · ${call.customer_attention.staff_memo}` : label;
}

function CallCard({ call, historical = false }: { call: WorkCall; historical?: boolean }) {
  const attention = attentionText(call);
  const status = call.status === 'IN_PROGRESS' ? '対応中' : call.status === 'MISSED' ? '不在' : call.status === 'DONE' ? '完了' : '未対応';
  return <View style={styles.callCard}>
    <View style={styles.cardTop}><Text style={styles.storeLabel}>{call.store_name}</Text><Text style={[styles.status, call.status === 'MISSED' && styles.statusMissed]}>{status}</Text></View>
    <Text style={styles.caller}>{call.customer_name || '新規のお客さま'}</Text>
    <Text style={styles.phone}>{call.from_phone}</Text>
    {attention ? <Text style={styles.attention}>{attention}</Text> : null}
    <Text style={styles.date}>{new Date(call.created_at).toLocaleString('ja-JP')}</Text>
    {!historical ? <Text style={styles.callHint}>着信への応答は、実機の通話連携ができてから利用できます。</Text> : null}
  </View>;
}

export function ReceptionScreen({ device, calls, history, busy, error, onRefresh, onToggleStore, onLogout, preview = false }: Props) {
  const [tab, setTab] = useState<Tab>('calls');
  const [selectedStore, setSelectedStore] = useState<number | null>(null);
  const receivingCount = device.stores.filter((store) => store.is_receiving).length;
  const visibleCalls = useMemo(() => {
    if (device.status !== 'active') return [];
    const receivingIds = new Set(device.stores.filter((store) => store.is_receiving).map((store) => store.id));
    return calls.filter((call) => receivingIds.has(call.store_id) && (selectedStore === null || call.store_id === selectedStore));
  }, [calls, device, selectedStore]);
  const visibleHistory = useMemo(() => history.filter((call) => selectedStore === null || call.store_id === selectedStore), [history, selectedStore]);

  return <SafeAreaView style={styles.safe}>
    <View style={styles.header}>
      <View><Text style={styles.kicker}>ROOMINK WORK</Text><Text style={styles.title}>{tab === 'calls' ? '着信' : tab === 'history' ? '履歴' : '受付店舗'}</Text></View>
      <Pressable onPress={onRefresh} disabled={busy} style={styles.refresh}><Text style={styles.refreshText}>{busy ? '更新中' : '更新'}</Text></Pressable>
    </View>
    <ScrollView contentContainerStyle={styles.content}>
      {preview ? <Text style={styles.preview}>ローカル画面プレビュー · 架空データ／実際の電話は鳴りません</Text> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {tab === 'calls' ? <>
        <View style={styles.deviceCard}><Text style={styles.deviceLabel}>{device.label}</Text><Text style={styles.deviceStatus}>{device.status === 'active' ? `${receivingCount}店舗で受付中` : '受付を停止中'}</Text></View>
        <StoreFilter stores={device.stores} selected={selectedStore} onSelect={setSelectedStore} />
        <Text style={styles.section}>{visibleCalls.length ? `${visibleCalls.length}件の着信` : '現在の着信'}</Text>
        {visibleCalls.length ? visibleCalls.map((call) => <CallCard key={call.id} call={call} />) : <Text style={styles.empty}>対応が必要な着信はありません</Text>}
        <Text style={styles.footnote}>Roomink Workから発信はできません。折り返しは店舗の受付回線から行ってください。</Text>
      </> : tab === 'history' ? <>
        <StoreFilter stores={device.stores} selected={selectedStore} onSelect={setSelectedStore} />
        {visibleHistory.length ? visibleHistory.map((call) => <CallCard key={call.id} call={call} historical />) : <Text style={styles.empty}>着信履歴はありません</Text>}
      </> : <>
        <Text style={styles.section}>この端末で受ける店舗</Text>
        <Text style={styles.description}>店舗ごとに受付中／休みを切り替えます。休みでも履歴は確認できます。</Text>
        {device.stores.map((store) => <Pressable key={store.id} onPress={() => onToggleStore(store)} disabled={busy} style={styles.storeRow}>
          <View style={styles.storeBody}><Text style={styles.storeName}>{store.name}</Text><Text style={styles.storeState}>{store.is_receiving ? '受付中' : '休み · 着信を出しません'}</Text></View>
          <Text style={[styles.storeAction, !store.is_receiving && styles.storeActionOff]}>{store.is_receiving ? '休みにする' : '受付を再開'}</Text>
        </Pressable>)}
        {busy ? <ActivityIndicator color={colors.green} /> : null}
        {__DEV__ ? <Link href="/lab" style={styles.developerLink}>模擬着信のローカル検証</Link> : null}
        {onLogout ? <Pressable onPress={onLogout} style={styles.logout}><Text style={styles.logoutText}>この端末からログアウト</Text></Pressable> : null}
      </>}
    </ScrollView>
    <View style={styles.tabBar}>{([['calls', '着信'], ['history', '履歴'], ['stores', '受付店舗']] as const).map(([value, label]) => <Pressable key={value} onPress={() => setTab(value)} style={[styles.tab, tab === value && styles.tabActive]}><Text style={[styles.tabText, tab === value && styles.tabTextActive]}>{label}</Text></Pressable>)}</View>
  </SafeAreaView>;
}

function StoreFilter({ stores, selected, onSelect }: { stores: Store[]; selected: number | null; onSelect: (id: number | null) => void }) {
  return <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filters}>
    <Pressable onPress={() => onSelect(null)} style={[styles.filter, selected === null && styles.filterActive]}><Text style={styles.filterText}>すべて</Text></Pressable>
    {stores.map((store) => <Pressable key={store.id} onPress={() => onSelect(store.id)} style={[styles.filter, selected === store.id && styles.filterActive]}><Text style={styles.filterText}>{store.name}</Text></Pressable>)}
  </ScrollView>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.paper }, header: { paddingHorizontal: 20, paddingTop: 14, paddingBottom: 12, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  kicker: { color: colors.green, fontSize: 11, fontWeight: '800', letterSpacing: 1.3 }, title: { color: colors.ink, fontSize: 31, fontWeight: '800' },
  refresh: { paddingVertical: 10, paddingHorizontal: 15, backgroundColor: colors.mint, borderRadius: 12 }, refreshText: { color: colors.green, fontWeight: '800' },
  content: { paddingHorizontal: 20, paddingBottom: 28, gap: 13 }, preview: { color: colors.warning, backgroundColor: '#fff1ea', borderRadius: 9, padding: 10, fontWeight: '700' },
  error: { color: colors.warning, backgroundColor: '#fff1ea', padding: 12, borderRadius: 10 }, deviceCard: { backgroundColor: colors.ink, padding: 19, borderRadius: 16, gap: 6 },
  deviceLabel: { color: '#fff', fontSize: 18, fontWeight: '800' }, deviceStatus: { color: '#cae7df', fontSize: 14 },
  filters: { gap: 8, paddingVertical: 4 }, filter: { backgroundColor: '#e8efed', paddingVertical: 9, paddingHorizontal: 14, borderRadius: 30 }, filterActive: { backgroundColor: '#bfe5db' }, filterText: { color: colors.ink, fontWeight: '700' },
  section: { color: colors.ink, fontSize: 17, fontWeight: '800', marginTop: 6 }, empty: { color: colors.muted, backgroundColor: colors.mint, padding: 20, borderRadius: 14 },
  callCard: { backgroundColor: '#fff', borderRadius: 17, borderLeftColor: colors.green, borderLeftWidth: 4, padding: 18, gap: 5 }, cardTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 },
  storeLabel: { color: colors.green, fontWeight: '800', flexShrink: 1 }, status: { color: colors.green, fontWeight: '800', fontSize: 12, backgroundColor: colors.mint, overflow: 'hidden', borderRadius: 7, paddingHorizontal: 8, paddingVertical: 4 }, statusMissed: { color: colors.warning, backgroundColor: '#fff1ea' },
  caller: { color: colors.ink, fontSize: 22, fontWeight: '800', marginTop: 5 }, phone: { color: colors.muted, fontSize: 15 }, attention: { color: colors.warning, backgroundColor: '#fff1ea', padding: 10, borderRadius: 9, fontWeight: '800', marginTop: 4 },
  date: { color: colors.muted, fontSize: 12, marginTop: 5 }, callHint: { color: colors.muted, fontSize: 12, marginTop: 8, lineHeight: 18 }, footnote: { color: colors.muted, fontSize: 12, lineHeight: 19, marginTop: 8 },
  description: { color: colors.muted, lineHeight: 21 }, storeRow: { backgroundColor: '#fff', padding: 16, borderRadius: 14, flexDirection: 'row', alignItems: 'center', gap: 8 }, storeBody: { flex: 1, gap: 4 }, storeName: { color: colors.ink, fontWeight: '800' }, storeState: { color: colors.muted, fontSize: 12 }, storeAction: { color: colors.green, fontWeight: '800', fontSize: 12 }, storeActionOff: { color: colors.warning },
  developerLink: { alignSelf: 'center', padding: 12, color: colors.green, fontWeight: '700' }, logout: { alignSelf: 'center', padding: 15, marginTop: 15 }, logoutText: { color: colors.muted }, tabBar: { flexDirection: 'row', padding: 8, gap: 6, borderTopColor: '#e1e9e5', borderTopWidth: 1, backgroundColor: '#fff' },
  tab: { flex: 1, alignItems: 'center', paddingVertical: 12, borderRadius: 11 }, tabActive: { backgroundColor: colors.mint }, tabText: { color: colors.muted, fontWeight: '700' }, tabTextActive: { color: colors.green, fontWeight: '800' },
});
