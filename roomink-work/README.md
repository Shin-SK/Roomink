# Roomink Work

Roomink Work is the iOS/Android **inbound-only** staff application. Phase 3 provides local app foundations only; it does not configure OS calling, push delivery, phone routing, Groundwire, staging, or production.

## Local run

1. Copy `.env.example` to `.env.local` and set the local machine's LAN IP address. A physical phone cannot use `localhost` to reach the development API.
2. Run `npm install` and then `npm start`.

The app intentionally refuses to make an API call until `EXPO_PUBLIC_ROOMINK_API_BASE_URL` is configured. Credentials and device tokens are stored with Expo SecureStore (Keychain on iOS and Android Keystore-backed storage where available), never in AsyncStorage.

## Included in this phase

- Personal-device login and selection of only the signed-in operator's permitted stores.
- Shared-device one-time linking and approval polling, with pending state stored securely across app restarts.
- Per-store reception on/off control, current calls with customer attention flags, a compact recent-call list, and manual refresh/heartbeat.
- System light/dark appearance, with a Roomink mark at the top and only Call/Settings tabs at the bottom. Settings holds receiving controls.
- Cursor-paged call history (100 records per request) and a virtualized list so a 300-call day does not truncate the history or mount every row at once.
- Foreground refresh every 15 seconds and immediately when returning to the app; this updates information only and cannot ring a locked or terminated device.
- No dial pad or outbound-call feature.

## Phase 4 local call lab

In development builds, open **模擬着信のローカル検証** from the reception screen. It simulates two receiving devices, three stores, simultaneous calls, pause/resume, and another subscribed device answering the same call. Run `npm run test:local-calls` for deterministic state tests. The lab sends no notification, makes no call, and uses no real customer data.

The development-only `/preview` route renders the **same call-list component as the authenticated app** with 320 fictitious A/B/C-store records. It opens in dark mode for visual review; Settings has a preview-only light/dark switch. The main screen shows one chronological call list (all/missed, with an optional store filter); device and per-store receiving controls are under Settings. Tapping a row opens details, never starts an outbound call. This preview does not connect to the backend or prove native calling. The `/lab` route remains a separate call-state simulator.

The app icon is derived from the existing Roomink vector mark. No new visual asset is needed for this local phase.

## Explicitly deferred

- PushKit/CallKit, Android OS calling UI, background or locked-device ringing.
- Carrier or Twilio/Groundwire changes, real-number testing, staging deployment, and production deployment.
- Server-side answer arbitration and native call/push adapters; the lab does not prove actual ringing or audio.
