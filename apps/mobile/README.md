# @helm/mobile

Expo SDK 52 + expo-router + Supabase Auth. The mobile surface of Helm — primary per the PRD.

Session 11 ships: auth, buffered chat, businesses list + create, approvals queue. SSE token streaming, haptics, Live Activity, and push notifications land in Session 12+.

## Local dev

```bash
# From repo root
pnpm install

# Create apps/mobile/.env
cat > apps/mobile/.env <<EOF
EXPO_PUBLIC_SUPABASE_URL=https://<ref>.supabase.co
EXPO_PUBLIC_SUPABASE_ANON_KEY=<anon key>
EXPO_PUBLIC_HELM_API_BASE=https://helm-api-ux69.onrender.com
EOF

pnpm --filter @helm/mobile start
# Scan the QR in Expo Go on your phone, or press 'i' for iOS simulator.
```

For iOS simulator you need Xcode + the iOS 18 simulator installed.

## What's deferred

- **SSE token streaming** — Session 12. RN's `fetch` doesn't give us `ReadableStream` uniformly across platforms; we either pull `react-native-sse` or use an `EventSource` polyfill.
- **Haptics** — Session 12 (via `expo-haptics`).
- **iOS Live Activity + Push Notifications** — Session 13. Requires an APN key + FCM service account + a custom native module (Live Activity isn't covered by a first-party Expo library yet).
- **Offline chat queue** — Session 14.
- **App Store builds** — EAS build once the surface is beta-ready.

## Backend note

The mobile app shares the same `/chat`, `/businesses`, `/approvals` endpoints as web. CORS on the backend already allowlists `http://localhost:3000`; mobile connections come through without an `Origin` header and go straight through.
