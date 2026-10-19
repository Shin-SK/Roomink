import { Link } from 'expo-router';
import { Image, ScrollView, StyleSheet, Text, useColorScheme, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

// Only the corresponding hosted environment may receive the user from this build.
const settingsUrls: Record<string, `https://${string}`> = {
  'https://api.roomink.net/api': 'https://app.roomink.net/op/settings/work-devices',
  'https://api-staging.roomink.net/api': 'https://staging.roomink.net/op/settings/work-devices',
};

export default function SetupScreen() {
  const dark = useColorScheme() === 'dark';
  const ink = dark ? '#f2f6f4' : '#182723';
  const muted = dark ? '#aab8b2' : '#5a6965';
  const accent = dark ? '#56c6b4' : '#167f70';
  const settingsUrl = settingsUrls[process.env.EXPO_PUBLIC_ROOMINK_API_BASE_URL?.replace(/\/$/, '') || ''];
  return <SafeAreaView style={[styles.safe, { backgroundColor: dark ? '#0d1212' : '#f7faf9' }]}>
    <ScrollView contentContainerStyle={styles.content}>
      <Link href="/" style={[styles.link, { color: accent }]}>‹ Workに戻る</Link>
      <Text style={[styles.title, { color: ink }]}>初期設定</Text>
      <View style={styles.appRow}>
        <Image source={require('../../assets/icon.png')} style={styles.icon} accessibilityLabel="Roomink Workのアプリアイコン" />
        <View style={styles.appCopy}><Text style={[styles.heading, { color: ink }]}>Roomink Work</Text><Text style={[styles.body, { color: muted }]}>これから使う受付アプリ</Text></View>
      </View>
      <View style={styles.appRow}>
        <Image source={require('../../assets/groundwire-app.jpg')} style={styles.icon} accessibilityLabel="Groundwireのアプリアイコン" />
        <View style={styles.appCopy}><Text style={[styles.heading, { color: ink }]}>Groundwire</Text><Text style={[styles.body, { color: muted }]}>削除せず、予備として残すアプリ</Text></View>
      </View>
      <Text style={[styles.heading, { color: ink }]}>Groundwireは残してください</Text>
      <Text style={[styles.body, { color: muted }]}>Workで受けられないときに戻すため、アプリと接続設定は削除しないでください。切り戻す前にGroundwireを開き、接続状態を確認します。</Text>
      <Text style={[styles.heading, { color: ink }]}>1. ログイン・端末連携</Text>
      <Text style={[styles.body, { color: muted }]}>個人端末は実際に使う人のRoominkアカウントでログインし、受ける店舗を選びます。共用端末は連携コードを発行し、管理者に承認してもらいます。</Text>
      <Text style={[styles.heading, { color: ink }]}>2. 対象店舗の着信をON</Text>
      <Text style={[styles.body, { color: muted }]}>Workの「設定」で店舗名と着信ONを確認してください。ログインや着信ONだけでは、店舗の受信先は変わりません。</Text>
      <Text style={[styles.heading, { color: ink }]}>3. 管理者が受信先を切り替える</Text>
      <Text style={[styles.body, { color: muted }]}>Roominkの設定をブラウザで開き、対象店舗の「Workに切り替える」を押します。ブラウザでもログインが必要です。管理権限のない方は管理者へ依頼してください。</Text>
      {settingsUrl ? <Link href={settingsUrl} style={[styles.link, { color: accent }]}>Roominkの受信先設定を開く ↗</Link> : <Text style={[styles.body, { color: muted }]}>この開発用アプリからは管理画面へ移動できません。</Text>}
      <Text style={[styles.heading, { color: ink }]}>4. 着信を確認して使用開始</Text>
      <Text style={[styles.body, { color: muted }]}>店舗番号へ電話をかけ、Workの着信、双方の声、Roominkの着信表示と履歴を確認します。</Text>
      <Text style={[styles.heading, { color: ink }]}>着信できないとき</Text>
      <Text style={[styles.body, { color: muted }]}>Groundwireの接続を確認し、管理者が同じ設定画面で「Groundwireに戻す」を押します。次の着信から有効です。通話中の電話は移動しません。</Text>
      <Text style={[styles.body, { color: muted }]}>設定画面を開けない場合は運営へ連絡してください。電話サービス全体の障害時は、運営と連携して元回線の転送を解除し、元の電話で受けます。解除方法と受ける電話は使用開始前に確認します。</Text>
    </ScrollView>
  </SafeAreaView>;
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { padding: 22, paddingBottom: 48, gap: 12 },
  title: { fontSize: 26, fontWeight: '800', marginBottom: 8 },
  heading: { fontSize: 17, fontWeight: '700', marginTop: 12 },
  body: { fontSize: 15, lineHeight: 24 },
  link: { fontSize: 15, fontWeight: '700', paddingVertical: 12 },
  appRow: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  appCopy: { flex: 1 },
  icon: { width: 64, height: 64, borderRadius: 14, borderWidth: 1, borderColor: '#dce5e1' },
});
