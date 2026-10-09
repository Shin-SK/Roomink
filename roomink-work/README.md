# Roomink Work

Roomink Work is the iOS/Android **inbound-only** staff application. Phase 3 provides local app foundations only; it does not configure OS calling, push delivery, phone routing, Groundwire, staging, or production.

## Local run

1. Copy `.env.example` to `.env.local` and set the local machine's LAN IP address. A physical phone cannot use `localhost` to reach the development API.
2. Run `npm install` and then `npm start`.

The app intentionally refuses to make an API call until `EXPO_PUBLIC_ROOMINK_API_BASE_URL` is configured. Credentials and device tokens are stored with Expo SecureStore (Keychain on iOS and Android Keystore-backed storage where available), never in AsyncStorage.

## Included in this phase

- Personal-device login and selection of only the signed-in operator's permitted stores.
- Shared-device one-time linking and approval polling, with pending state stored securely across app restarts.
- Per-store reception on/off control, current calls with customer attention flags, recent call history, and manual refresh/heartbeat.
- No dial pad or outbound-call feature.

## Explicitly deferred

- PushKit/CallKit, Android OS calling UI, background or locked-device ringing.
- Carrier or Twilio/Groundwire changes, real-number testing, staging deployment, and production deployment.
