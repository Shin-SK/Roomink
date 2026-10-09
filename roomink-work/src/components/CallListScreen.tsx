import { useMemo, useState } from 'react';
import { Link } from 'expo-router';
import { FlatList, Image, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, useColorScheme, View } from 'react-native';
import { callList } from '../lib/call-list';
import type { Device, Store, WorkCall } from '../lib/roomink';

type Props = {
  device: Device;
  calls: WorkCall[];
  history: WorkCall[];
  missedHistory?: WorkCall[];
  missedLoaded?: boolean;
  hasMoreAll?: boolean;
  hasMoreMissed?: boolean;
  loadingMore?: boolean;
  onLoadMore?: (missedOnly: boolean) => void;
  onMissedOnlyChange?: (missedOnly: boolean) => void;
  busy: boolean;
  error: string | null;
  onRefresh: () => void;
  onToggleStore: (store: Store) => void;
  onLogout?: () => void;
  preview?: boolean;
};

const palettes = {
  light: { bg: '#f7faf9', surface: '#ffffff', text: '#182723', muted: '#5a6965', border: '#e2e9e6', accent: '#167f70', accentBg: '#e5f3ef', red: '#b13e42', caution: '#9b4728', cautionBg: '#fff0e8' },
  dark: { bg: '#0d1212', surface: '#171e1e', text: '#f2f6f4', muted: '#aab8b2', border: '#2d3836', accent: '#56c6b4', accentBg: '#1b3833', red: '#ff6d76', caution: '#ffb18b', cautionBg: '#3d2721' },
};

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
  if (Number.isNaN(date.getTime())) return '';
  const today = new Date();
  if (date.toDateString() === today.toDateString()) return date.toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' });
  return date.toLocaleDateString('ja-JP', { month: 'numeric', day: 'numeric' });
}

function attention(call: WorkCall) {
  const flag = call.customer_attention?.flag;
  return flag && flag !== 'NONE' ? flag === 'BAN' ? '出禁' : '要注意' : null;
}

function ClockIcon({ color }: { color: string }) {
  return <View style={{ width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: color, alignItems: 'center', justifyContent: 'center' }}><View style={{ position: 'absolute', width: 2, height: 7, backgroundColor: color, top: 3, left: 9 }} /><View style={{ position: 'absolute', width: 7, height: 2, backgroundColor: color, top: 10, left: 9 }} /></View>;
}

export function CallListScreen({ device, calls, history, missedHistory, missedLoaded = true, hasMoreAll = false, hasMoreMissed = false, loadingMore = false, onLoadMore, onMissedOnlyChange, busy, error, onRefresh, onToggleStore, onLogout, preview = false }: Props) {
  const systemScheme = useColorScheme();
  const [previewDark, setPreviewDark] = useState(true);
  const dark = preview ? previewDark : systemScheme === 'dark';
  const palette = dark ? palettes.dark : palettes.light;
  const styles = useMemo(() => makeStyles(palette), [palette]);
  const [section, setSection] = useState<'calls' | 'settings'>('calls');
  const [missedOnly, setMissedOnly] = useState(false);
  const [selectedStore, setSelectedStore] = useState<number | null>(null);
  const [showStoreFilter, setShowStoreFilter] = useState(false);
  const [selectedCall, setSelectedCall] = useState<number | null>(null);
  // The all-calls poll can receive a new missed call before the dedicated missed page refreshes.
  const rows = useMemo(() => callList(device, calls, missedOnly ? [...(missedHistory ?? []), ...history] : history, selectedStore, missedOnly), [device, calls, history, missedHistory, selectedStore, missedOnly]);
  const detail = rows.find((row) => row.id === selectedCall);
  const hasMore = missedOnly ? hasMoreMissed : hasMoreAll;
  const receivingCount = device.stores.filter((store) => store.is_receiving && store.is_entitled !== false).length;

  const header = <>
    {preview ? <Text style={styles.preview}>画面プレビュー · 架空データ／実際の電話は鳴りません</Text> : null}
    {error ? <Text style={styles.error}>{error}</Text> : null}
    <View style={styles.segment}>
      <Pressable onPress={() => { setMissedOnly(false); onMissedOnlyChange?.(false); }} style={[styles.segmentButton, !missedOnly && styles.segmentActive]}><Text style={[styles.segmentText, !missedOnly && styles.segmentTextActive]}>すべて</Text></Pressable>
      <Pressable onPress={() => { setMissedOnly(true); onMissedOnlyChange?.(true); }} style={[styles.segmentButton, missedOnly && styles.segmentActive]}><Text style={[styles.segmentText, missedOnly && styles.segmentTextActive]}>不在</Text></Pressable>
    </View>
    {device.stores.length > 1 ? <><Pressable onPress={() => setShowStoreFilter((value) => !value)} style={styles.filterTrigger}><Text style={styles.filterText}>{selectedStore === null ? 'すべての店舗' : device.stores.find((store) => store.id === selectedStore)?.name || 'すべての店舗'} ▾</Text></Pressable>
      {showStoreFilter ? <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filters}><Pressable onPress={() => { setSelectedStore(null); setShowStoreFilter(false); }} style={styles.filterPill}><Text style={styles.filterText}>すべて</Text></Pressable>{device.stores.filter((store) => store.is_entitled !== false).map((store) => <Pressable key={store.id} onPress={() => { setSelectedStore(store.id); setShowStoreFilter(false); }} style={styles.filterPill}><Text style={styles.filterText}>{store.name}</Text></Pressable>)}</ScrollView> : null}
    </> : null}
  </>;

  function renderRow({ item: call }: { item: WorkCall }) {
    const flag = attention(call);
    return <Pressable onPress={() => setSelectedCall(call.id)} style={styles.callRow} accessibilityLabel={`${call.from_phone} ${call.customer_name || '新規のお客さま'} ${statusLabel(call.status)} ${call.store_name}`}>
      <View style={styles.firstLine}><Text style={[styles.phone, call.status === 'MISSED' && styles.missed]} numberOfLines={1}>{call.from_phone}</Text><Text style={styles.storeChip} numberOfLines={1}>{call.store_name}</Text><Text style={styles.time}>{callTime(call.created_at)}</Text></View>
      <View style={styles.secondLine}>{flag ? <Text style={styles.flag}>{flag}</Text> : null}<Text style={styles.customer} numberOfLines={1}>{call.customer_name || '新規のお客さま'}</Text><Text style={styles.status}>{statusLabel(call.status)}</Text><Text style={styles.chevron}>›</Text></View>
    </Pressable>;
  }

  return <SafeAreaView style={styles.safe}>
    <View style={styles.topBar}>
      <View style={styles.topSide}>{detail && section === 'calls' ? <Pressable onPress={() => setSelectedCall(null)}><Text style={styles.topAction}>‹ 戻る</Text></Pressable> : null}</View>
      <Image source={require('../../assets/brand-mark.png')} style={styles.mark} accessibilityLabel="Roomink" />
      <View style={styles.topSide}>{section === 'calls' && !detail ? <Pressable onPress={onRefresh} disabled={busy}><Text style={styles.topAction}>{busy ? '更新中' : '↻ 更新'}</Text></Pressable> : null}</View>
    </View>
    {section === 'settings' ? <ScrollView contentContainerStyle={styles.content}>
      {preview ? <Text style={styles.preview}>画面プレビュー · 架空データ／実際の電話は鳴りません</Text> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <View style={styles.deviceRow}><Text style={styles.deviceName}>{device.label}</Text><Text style={styles.deviceStatus}>{device.status === 'active' ? `${receivingCount}店舗で受付中` : '受付停止中'}</Text></View>
      <Text style={styles.groupTitle}>着信を受ける店舗</Text>
      <Text style={styles.description}>休みの店舗でも履歴は確認できます。</Text>
      <View style={styles.group}>{device.stores.filter((store) => store.is_entitled !== false).map((store) => <Pressable key={store.id} onPress={() => onToggleStore(store)} disabled={busy} style={styles.settingRow}><View style={styles.grow}><Text style={styles.settingName}>{store.name}</Text><Text style={styles.secondary}>{store.is_receiving ? '受付中' : '休み'}</Text></View><Text style={[styles.settingAction, !store.is_receiving && styles.paused]}>{store.is_receiving ? '休みにする' : '受付を再開'}</Text></Pressable>)}</View>
      {preview ? <Pressable onPress={() => setPreviewDark((value) => !value)} style={styles.themeToggle}><Text style={styles.settingName}>画面確認用：{dark ? 'ダーク' : 'ライト'}表示</Text><Text style={styles.settingAction}>切り替え</Text></Pressable> : null}
      <Text style={styles.description}>アプリから発信はできません。折り返しは店舗の受付回線から行ってください。</Text>
      {__DEV__ ? <Link href="/lab" style={styles.developerLink}>開発用の模擬着信テスト</Link> : null}
      {onLogout ? <Pressable onPress={onLogout} style={styles.logout}><Text style={styles.secondary}>この端末からログアウト</Text></Pressable> : null}
    </ScrollView> : detail ? <ScrollView contentContainerStyle={styles.content}>
      {preview ? <Text style={styles.preview}>画面プレビュー · 架空データ／実際の電話は鳴りません</Text> : null}
      <Text style={styles.detailPhone}>{detail.from_phone}</Text><Text style={styles.detailName}>{detail.customer_name || '新規のお客さま'}</Text>
      <View style={styles.group}><View style={styles.detailRow}><Text style={styles.secondary}>店舗</Text><Text style={styles.value}>{detail.store_name}</Text></View><View style={styles.detailRow}><Text style={styles.secondary}>状態</Text><Text style={styles.value}>{statusLabel(detail.status)}</Text></View><View style={styles.detailRow}><Text style={styles.secondary}>日時</Text><Text style={styles.value}>{new Date(detail.created_at).toLocaleString('ja-JP')}</Text></View></View>
      {attention(detail) ? <Text style={styles.attention}>{attention(detail)}{detail.customer_attention?.staff_memo ? ` · ${detail.customer_attention.staff_memo}` : ''}</Text> : null}
      <Text style={styles.description}>折り返しは店舗の受付回線から行ってください。</Text>
    </ScrollView> : <FlatList data={rows} keyExtractor={(call) => String(call.id)} renderItem={renderRow} contentContainerStyle={styles.listContent} ListHeaderComponent={header} ListEmptyComponent={<Text style={styles.empty}>{missedOnly && !missedLoaded ? '不在着信を読み込み中…' : missedOnly ? '不在着信はありません' : '通話はまだありません'}</Text>} ListFooterComponent={hasMore ? <Pressable onPress={() => onLoadMore?.(missedOnly)} disabled={loadingMore} style={styles.loadMore}><Text style={styles.filterText}>{loadingMore ? '読み込み中…' : '過去の通話を読み込む'}</Text></Pressable> : null} onEndReached={() => { if (hasMore && !loadingMore) onLoadMore?.(missedOnly); }} onEndReachedThreshold={0.4} initialNumToRender={18} maxToRenderPerBatch={20} windowSize={7} />}
    <View style={styles.tabBar}><Pressable onPress={() => { setSection('calls'); setSelectedCall(null); }} style={styles.tab} accessibilityLabel="通話"><ClockIcon color={section === 'calls' ? palette.accent : palette.muted} /><Text style={[styles.tabText, section === 'calls' && styles.tabTextActive]}>通話</Text></Pressable><Pressable onPress={() => { setSection('settings'); setSelectedCall(null); }} style={styles.tab} accessibilityLabel="設定"><Text style={[styles.gear, section === 'settings' && styles.gearActive]}>⚙</Text><Text style={[styles.tabText, section === 'settings' && styles.tabTextActive]}>設定</Text></Pressable></View>
  </SafeAreaView>;
}

function makeStyles(c: typeof palettes.light) { return StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.bg }, topBar: { height: 55, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 18, borderBottomWidth: 1, borderBottomColor: c.border }, topSide: { width: 80 }, mark: { width: 29, height: 29 }, topAction: { color: c.accent, fontSize: 13, fontWeight: '700', textAlign: 'right' },
  listContent: { paddingHorizontal: 16, paddingBottom: 32, flexGrow: 1 }, content: { padding: 18, paddingBottom: 36, gap: 13 }, preview: { color: c.caution, backgroundColor: c.cautionBg, borderRadius: 8, padding: 9, fontSize: 11, marginVertical: 9 }, error: { color: c.red, padding: 10, backgroundColor: c.cautionBg, borderRadius: 8 },
  segment: { flexDirection: 'row', alignSelf: 'flex-start', padding: 3, backgroundColor: c.surface, borderRadius: 10, marginVertical: 10 }, segmentButton: { paddingVertical: 7, paddingHorizontal: 16, borderRadius: 8 }, segmentActive: { backgroundColor: c.accentBg }, segmentText: { color: c.muted, fontWeight: '700' }, segmentTextActive: { color: c.accent },
  filterTrigger: { alignSelf: 'flex-start', paddingVertical: 8, marginBottom: 4 }, filterText: { color: c.accent, fontSize: 12, fontWeight: '700' }, filters: { gap: 7, paddingBottom: 8 }, filterPill: { padding: 9, backgroundColor: c.surface, borderRadius: 20 },
  callRow: { minHeight: 72, paddingVertical: 11, paddingHorizontal: 4, borderBottomWidth: 1, borderBottomColor: c.border, gap: 5 }, firstLine: { flexDirection: 'row', alignItems: 'center', gap: 7 }, phone: { color: c.text, fontSize: 17, fontWeight: '800', flexShrink: 1 }, storeChip: { color: c.muted, fontSize: 10, flex: 1 }, time: { color: c.muted, fontSize: 11, marginLeft: 'auto' },
  secondLine: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingRight: 2 }, flag: { color: c.caution, backgroundColor: c.cautionBg, fontSize: 10, fontWeight: '800', overflow: 'hidden', borderRadius: 4, paddingHorizontal: 4, paddingVertical: 2 }, customer: { color: c.muted, fontSize: 13, flex: 1 }, status: { color: c.muted, fontSize: 12 }, missed: { color: c.red }, chevron: { color: c.muted, fontSize: 19, marginLeft: 3 },
  empty: { color: c.muted, textAlign: 'center', padding: 25 }, loadMore: { padding: 18, alignItems: 'center' }, tabBar: { flexDirection: 'row', backgroundColor: c.surface, borderTopWidth: 1, borderTopColor: c.border, paddingVertical: 6 }, tab: { flex: 1, alignItems: 'center', gap: 3, paddingVertical: 5 }, tabText: { color: c.muted, fontSize: 11, fontWeight: '700' }, tabTextActive: { color: c.accent }, gear: { color: c.muted, fontSize: 24, lineHeight: 25 }, gearActive: { color: c.accent },
  deviceRow: { padding: 16, backgroundColor: c.surface, borderRadius: 12 }, deviceName: { color: c.text, fontSize: 16, fontWeight: '800' }, deviceStatus: { color: c.muted, marginTop: 5 }, groupTitle: { color: c.text, fontSize: 16, fontWeight: '800', marginTop: 7 }, description: { color: c.muted, fontSize: 12, lineHeight: 19 }, group: { backgroundColor: c.surface, borderRadius: 12, overflow: 'hidden' },
  settingRow: { flexDirection: 'row', alignItems: 'center', padding: 15, borderBottomWidth: 1, borderBottomColor: c.border }, grow: { flex: 1 }, settingName: { color: c.text, fontWeight: '700' }, secondary: { color: c.muted, fontSize: 12, marginTop: 4 }, settingAction: { color: c.accent, fontSize: 12, fontWeight: '700' }, paused: { color: c.caution }, themeToggle: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 14, backgroundColor: c.surface, borderRadius: 11 }, developerLink: { alignSelf: 'center', padding: 12, color: c.accent }, logout: { alignSelf: 'center', padding: 15 },
  detailPhone: { color: c.text, fontSize: 25, fontWeight: '800', textAlign: 'center', marginTop: 22 }, detailName: { color: c.muted, fontSize: 16, textAlign: 'center', marginBottom: 18 }, detailRow: { flexDirection: 'row', justifyContent: 'space-between', padding: 15, borderBottomWidth: 1, borderBottomColor: c.border, gap: 8 }, value: { color: c.text, fontWeight: '700', flexShrink: 1, textAlign: 'right' }, attention: { color: c.caution, backgroundColor: c.cautionBg, padding: 12, borderRadius: 9 },
}); }
