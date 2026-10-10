import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'expo-router';
import { ActivityIndicator, Alert, AppState, Platform, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, useColorScheme, View } from 'react-native';
import { CallListScreen } from '../components/CallListScreen';
import { clearPendingLink, clearToken, claimSharedLink, createSharedLink, Device, getPendingLink, getToken, getVoiceAccessToken, loginPersonal, lookupPersonalStores, PendingLink, Store, WorkApiError, WorkCall, workRequest } from '../lib/roomink';
import { registerForIncomingCalls, unregisterIncomingCalls, VoiceRegistrationState } from '../lib/voice';

type Mode = 'personal' | 'shared';

const colors = { ink: '#183733', green: '#47756f', mint: '#edf5f2', paper: '#fbfcfb', warning: '#b5532e', muted: '#65716f' };

function mergeHistory(previous: WorkCall[], incoming: WorkCall[]) {
  return [...new Map([...previous, ...incoming].map((call) => [call.id, call])).values()];
}

export default function HomeScreen() {
  const [loading, setLoading] = useState(true);
  const [device, setDevice] = useState<Device | null>(null);
  const [calls, setCalls] = useState<WorkCall[]>([]);
  const [history, setHistory] = useState<WorkCall[]>([]);
  const [historyCursor, setHistoryCursor] = useState<string | null>(null);
  const [missedHistory, setMissedHistory] = useState<WorkCall[]>([]);
  const [missedCursor, setMissedCursor] = useState<string | null>(null);
  const [missedLoaded, setMissedLoaded] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const loadingMoreRef = useRef(false);
  const historyInitializedRef = useRef(false);
  const missedInitializedRef = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>('personal');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [label, setLabel] = useState('受付端末');
  const [stores, setStores] = useState<Store[]>([]);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [link, setLink] = useState<PendingLink | null>(null);
  const [busy, setBusy] = useState(false);
  const [voiceState, setVoiceState] = useState<VoiceRegistrationState | null>(null);
  const deviceConnected = device !== null;
  const canReceiveVoice = device?.status === 'active' && device.stores.some(
    (store) => store.is_receiving && store.is_entitled,
  );

  const refreshMissed = useCallback(async () => {
    const page = await workRequest<{ calls: WorkCall[]; next_cursor: string | null }>('/work/history/?status=missed');
    setMissedHistory((previous) => mergeHistory(previous, page.calls));
    if (!missedInitializedRef.current) { setMissedCursor(page.next_cursor); missedInitializedRef.current = true; }
    setMissedLoaded(true);
  }, []);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const nextDevice = await workRequest<Device>('/work/me/');
      const nextCalls = await workRequest<{ calls: WorkCall[] }>('/work/calls/');
      const nextHistory = await workRequest<{ calls: WorkCall[]; next_cursor: string | null }>('/work/history/');
      setDevice(nextDevice); setCalls(nextCalls.calls);
      setHistory((previous) => mergeHistory(previous, nextHistory.calls));
      if (!historyInitializedRef.current) { setHistoryCursor(nextHistory.next_cursor); historyInitializedRef.current = true; }
      await workRequest('/work/heartbeat/', { method: 'POST', body: '{}' });
    } catch (reason) {
      if (reason instanceof WorkApiError && (reason.status === 401 || reason.status === 403)) {
        await clearToken();
        setDevice(null); setCalls([]); setHistory([]); setMissedHistory([]); setHistoryCursor(null); setMissedCursor(null); setMissedLoaded(false);
        historyInitializedRef.current = false; missedInitializedRef.current = false;
        setError('端末の認証が失効しました。もう一度連携してください。');
      } else {
        setError(reason instanceof Error ? reason.message : '読み込みに失敗しました。');
      }
    }
  }, []);

  async function loadMoreHistory(missedOnly: boolean) {
    if (loadingMoreRef.current) return;
    const cursor = missedOnly ? missedCursor : historyCursor;
    if (!cursor) return;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    try {
      const query = `cursor=${encodeURIComponent(cursor)}${missedOnly ? '&status=missed' : ''}`;
      const page = await workRequest<{ calls: WorkCall[]; next_cursor: string | null }>(`/work/history/?${query}`);
      if (missedOnly) { setMissedHistory((previous) => mergeHistory(previous, page.calls)); setMissedCursor(page.next_cursor); }
      else { setHistory((previous) => mergeHistory(previous, page.calls)); setHistoryCursor(page.next_cursor); }
    } catch (reason) { setError(reason instanceof Error ? reason.message : '履歴を読み込めませんでした。'); }
    finally { loadingMoreRef.current = false; setLoadingMore(false); }
  }

  useEffect(() => { (async () => {
    try {
      if (Platform.OS === 'web') return;
      if (await getToken()) await refresh();
      else setLink(await getPendingLink());
    } catch (reason) { setError(reason instanceof Error ? reason.message : '端末情報を読み込めませんでした。'); }
    finally { setLoading(false); }
  })(); }, [refresh]);

  useEffect(() => {
    if (!deviceConnected) return;
    let inFlight = false;
    const tick = async () => {
      if (AppState.currentState !== 'active' || inFlight) return;
      inFlight = true;
      try { await refresh(); } finally { inFlight = false; }
    };
    const interval = setInterval(() => { void tick(); }, 15000);
    const subscription = AppState.addEventListener('change', (state) => { if (state === 'active') void tick(); });
    return () => { clearInterval(interval); subscription.remove(); };
  }, [deviceConnected, refresh]);

  useEffect(() => {
    if (!canReceiveVoice || Platform.OS === 'web') {
      void unregisterIncomingCalls().catch(() => {});
      return;
    }
    let cancelled = false;
    const configureVoice = async () => {
      try {
        const { token } = await getVoiceAccessToken();
        if (!cancelled) {
          await registerForIncomingCalls(token, (state) => {
            if (!cancelled) setVoiceState(state);
          });
        }
      } catch (reason) {
        if (!cancelled) {
          setVoiceState({ kind: 'error', message: reason instanceof Error ? reason.message : '着信の初期化に失敗しました。' });
        }
      }
    };
    void configureVoice();
    const timer = setInterval(() => { void configureVoice(); }, 50 * 60 * 1000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [canReceiveVoice]);

  async function findStores() {
    setBusy(true); setError(null);
    try {
      const result = await lookupPersonalStores(username, password);
      setStores(result.stores); setSelectedIds(result.stores.map((store) => store.id));
    } catch (reason) { setError(reason instanceof Error ? reason.message : '店舗を確認できませんでした。'); }
    finally { setBusy(false); }
  }

  async function completePersonalLogin() {
    setBusy(true); setError(null);
    try { setDevice(await loginPersonal({ username, password, label, platform: Platform.OS === 'android' ? 'android' : 'ios', storeIds: selectedIds })); setPassword(''); await refresh(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : '端末を連携できませんでした。'); }
    finally { setBusy(false); }
  }

  async function startSharedLink() {
    setBusy(true); setError(null);
    try { setLink(await createSharedLink(label, Platform.OS === 'android' ? 'android' : 'ios')); }
    catch (reason) { setError(reason instanceof Error ? reason.message : '連携コードを作れませんでした。'); }
    finally { setBusy(false); }
  }

  async function checkSharedLink() {
    if (!link) return;
    setBusy(true); setError(null);
    try {
      const result = await claimSharedLink(link.request_id, link.claim_secret);
      if (result.status === 'approved') { setLink(null); setDevice(result.device ?? null); await refresh(); }
      else Alert.alert('承認待ち', '管理画面でコードを承認すると、この画面で連携が完了します。');
    } catch (reason) { setError(reason instanceof Error ? reason.message : '連携状態を確認できませんでした。'); }
    finally { setBusy(false); }
  }

  async function toggleStore(store: Store) {
    if (!device || busy) return;
    setBusy(true);
    const updated = device.stores.map((row) => row.id === store.id ? { ...row, is_receiving: !row.is_receiving } : row);
    setDevice({ ...device, stores: updated });
    try { setDevice(await workRequest<Device>('/work/receiving/', { method: 'POST', body: JSON.stringify({ stores: [{ store_id: store.id, is_receiving: !store.is_receiving }] }) })); await refresh(); }
    catch (reason) { await refresh(); setError(reason instanceof Error ? reason.message : '受付状態を更新できませんでした。'); }
    finally { setBusy(false); }
  }

  if (loading) return <Centered><ActivityIndicator color={colors.green} /></Centered>;
  if (!device) return <AuthScreen {...{ mode, setMode, username, setUsername, password, setPassword, label, setLabel, stores, selectedIds, setSelectedIds, link, busy, error, findStores, completePersonalLogin, startSharedLink, checkSharedLink }} />;
  const voiceNotice = !canReceiveVoice ? null : voiceState?.kind === 'registered'
    ? 'iPhoneの着信登録が完了しました。'
    : voiceState?.kind === 'registering'
      ? 'iPhoneの着信登録を準備しています。'
      : voiceState?.kind === 'error' ? voiceState.message : null;
  return <CallListScreen device={device} calls={calls} history={history} missedHistory={missedHistory} missedLoaded={missedLoaded} hasMoreAll={historyCursor !== null} hasMoreMissed={missedCursor !== null} loadingMore={loadingMore} onLoadMore={loadMoreHistory} onMissedOnlyChange={async (value) => { if (value && !missedLoaded) { try { await refreshMissed(); } catch (reason) { setError(reason instanceof Error ? reason.message : '不在着信を読み込めませんでした。'); } } }} busy={busy} error={error || voiceNotice} onRefresh={async () => { await refresh(); if (missedLoaded) await refreshMissed(); }} onToggleStore={toggleStore} onLogout={async () => { try { await unregisterIncomingCalls(); } catch { /* Local logout must still revoke the app session. */ } await clearToken(); setDevice(null); setCalls([]); setHistory([]); setMissedHistory([]); setHistoryCursor(null); setMissedCursor(null); setMissedLoaded(false); historyInitializedRef.current = false; missedInitializedRef.current = false; }} />;
}

function AuthScreen(props: any) {
  const personalReady = props.stores.length > 0;
  const webPreview = Platform.OS === 'web';
  const dark = useColorScheme() === 'dark';
  const surface = dark ? '#171e1e' : '#ffffff';
  const foreground = dark ? '#f2f6f4' : colors.ink;
  const muted = dark ? '#aab8b2' : colors.muted;
  const accent = dark ? '#56c6b4' : colors.green;
  return <SafeAreaView style={[styles.safe, dark && { backgroundColor: '#0d1212' }]}><ScrollView contentContainerStyle={styles.authPage}><Text style={[styles.kicker, { color: accent }]}>ROOMINK WORK</Text><Text style={[styles.title, { color: foreground }]}>受信専用の受付端末</Text><Text style={[styles.lead, { color: muted }]}>このアプリから電話を発信しません。着信情報の確認と受付状態の管理だけを行います。</Text>
    <View style={styles.tabs}><Pressable onPress={() => props.setMode('personal')} style={[styles.tab, { backgroundColor: props.mode === 'personal' ? (dark ? '#1b3833' : '#cde1da') : surface }]}><Text style={{ color: foreground }}>個人端末</Text></Pressable><Pressable onPress={() => props.setMode('shared')} style={[styles.tab, { backgroundColor: props.mode === 'shared' ? (dark ? '#1b3833' : '#cde1da') : surface }]}><Text style={{ color: foreground }}>共用端末</Text></Pressable></View>
    {webPreview ? <Notice text="ブラウザでは画面のプレビューのみ可能です。端末の連携にはiOSまたはAndroidのアプリが必要です。" /> : null}
    {props.error ? <Notice text={props.error} /> : null}
    <TextInput value={props.label} onChangeText={props.setLabel} placeholder="端末名" placeholderTextColor={muted} style={[styles.input, { backgroundColor: surface, color: foreground }]} />
    {props.mode === 'personal' ? <>
      <TextInput value={props.username} editable={!webPreview} onChangeText={(value) => { props.setUsername(value); props.setStores([]); props.setSelectedIds([]); }} placeholder="ユーザー名" placeholderTextColor={muted} autoCapitalize="none" style={[styles.input, { backgroundColor: surface, color: foreground }]} />
      <TextInput value={props.password} editable={!webPreview} onChangeText={(value) => { props.setPassword(value); props.setStores([]); props.setSelectedIds([]); }} placeholder="パスワード" placeholderTextColor={muted} secureTextEntry style={[styles.input, { backgroundColor: surface, color: foreground }]} />
      {!personalReady ? <Primary label="所属店舗を確認" disabled={webPreview || !props.username || !props.password || props.busy} onPress={props.findStores} /> : <>
        <Text style={[styles.section, { color: foreground }]}>この端末で受ける店舗</Text>{props.stores.map((store: Store) => <Pressable key={store.id} onPress={() => props.setSelectedIds(props.selectedIds.includes(store.id) ? props.selectedIds.filter((id: number) => id !== store.id) : [...props.selectedIds, store.id])} style={styles.checkRow}><Text style={{ color: foreground }}>{props.selectedIds.includes(store.id) ? '✓' : '○'}</Text><Text style={[styles.storeName, { color: foreground }]}>{store.name}</Text></Pressable>)}<Primary label="この端末を連携" disabled={webPreview || !props.selectedIds.length || props.busy} onPress={props.completePersonalLogin} /></>}
    </> : <>{!props.link ? <Primary label="連携コードを表示" disabled={webPreview || !props.label || props.busy} onPress={props.startSharedLink} /> : <View style={[styles.linkBox, { backgroundColor: surface }]}><Text style={[styles.meta, { color: muted }]}>管理画面で次のコードを承認してください</Text><Text style={[styles.code, { color: foreground }]}>{props.link.code}</Text><Primary label="承認状態を確認" disabled={webPreview || props.busy} onPress={props.checkSharedLink} /><Pressable onPress={async () => { await clearPendingLink(); props.setLink(null); }}><Text style={{ color: accent }}>連携をやり直す</Text></Pressable></View>}</>}
    {__DEV__ ? <><Link href="/preview" style={[styles.labLink, { color: accent }]}>実際の受付画面をプレビュー</Link><Link href="/lab" style={[styles.labLink, { color: accent }]}>模擬着信のローカル検証</Link></> : null}
  </ScrollView></SafeAreaView>;
}

function Primary({ label, disabled, onPress }: { label: string; disabled: boolean; onPress: () => void }) { return <Pressable onPress={onPress} disabled={disabled} style={[styles.primary, disabled && styles.disabled]}><Text style={styles.primaryText}>{label}</Text></Pressable>; }
function Notice({ text }: { text: string }) { return <View style={styles.noticeBox}><Text>{text}</Text></View>; }
function Centered({ children }: { children: React.ReactNode }) { const dark = useColorScheme() === 'dark'; return <SafeAreaView style={[styles.safe, styles.center, dark && { backgroundColor: '#0d1212' }]}>{children}</SafeAreaView>; }

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.paper }, page: { padding: 20, gap: 12 }, authPage: { padding: 24, gap: 14 }, center: { alignItems: 'center', justifyContent: 'center' }, header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }, kicker: { color: colors.green, fontWeight: '800', letterSpacing: 1.5, fontSize: 12 }, title: { color: colors.ink, fontSize: 30, fontWeight: '800', marginTop: 4 }, lead: { color: colors.muted, lineHeight: 22 }, smallButton: { backgroundColor: colors.mint, paddingVertical: 9, paddingHorizontal: 14, borderRadius: 10 }, status: { backgroundColor: colors.ink, padding: 18, borderRadius: 16 }, statusTitle: { color: 'white', fontWeight: '800', fontSize: 18 }, statusText: { color: '#cfe2dc', marginTop: 4 }, section: { color: colors.ink, fontSize: 17, fontWeight: '800', marginTop: 12 }, callCard: { backgroundColor: 'white', padding: 16, borderRadius: 14, borderLeftWidth: 4, borderLeftColor: colors.warning, gap: 4 }, historyRow: { backgroundColor: 'white', padding: 14, borderRadius: 12, gap: 4 }, filterRow: { gap: 8 }, filter: { backgroundColor: '#edf0ef', paddingVertical: 8, paddingHorizontal: 12, borderRadius: 20 }, filterActive: { backgroundColor: '#cde1da' }, storeName: { color: colors.ink, fontWeight: '800' }, caller: { color: colors.ink, fontSize: 18, fontWeight: '700' }, meta: { color: colors.muted, fontSize: 13 }, notice: { color: colors.warning, fontSize: 12, marginTop: 6 }, empty: { backgroundColor: colors.mint, padding: 18, borderRadius: 14 }, storeRow: { padding: 16, borderRadius: 14, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }, storeOn: { backgroundColor: '#e7f5ee' }, storeOff: { backgroundColor: '#eee' }, toggle: { color: colors.green, fontWeight: '800' }, logout: { alignSelf: 'center', marginTop: 24, padding: 12 }, labLink: { alignSelf: 'center', color: colors.green, fontWeight: '700', padding: 10 }, tabs: { flexDirection: 'row', gap: 8 }, tab: { flex: 1, padding: 12, alignItems: 'center', backgroundColor: '#edf0ef', borderRadius: 10 }, tabActive: { backgroundColor: '#cde1da' }, input: { backgroundColor: 'white', borderWidth: 1, borderColor: '#d7dfdc', padding: 14, borderRadius: 10, fontSize: 16 }, primary: { backgroundColor: colors.green, padding: 15, alignItems: 'center', borderRadius: 12, marginTop: 4 }, disabled: { opacity: .45 }, primaryText: { color: 'white', fontWeight: '800' }, checkRow: { flexDirection: 'row', gap: 12, paddingVertical: 12, alignItems: 'center' }, linkBox: { backgroundColor: colors.mint, padding: 20, borderRadius: 16, gap: 12, alignItems: 'center' }, code: { color: colors.ink, fontSize: 30, letterSpacing: 4, fontWeight: '900' }, noticeBox: { backgroundColor: '#fff0ea', borderRadius: 10, padding: 12 }
});
