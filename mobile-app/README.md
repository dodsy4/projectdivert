# Project Divert Mobile App (MVP Scaffold)

This mobile app scaffold connects directly to your existing backend APIs:

- `POST /api/v1/auth/login`
- `POST /api/v1/waste-requests`
- `GET /api/v1/waste-requests/:id`
- `GET /api/v1/waste-requests/:id/location/latest`
- `GET /api/v1/waste-requests/:id/events` (SSE realtime stream)
- `POST /api/v1/waste-requests/:id/status` (driver/admin simulation)
- `POST /api/v1/waste-requests/:id/location` (driver/admin simulation)
- `POST /api/v1/push-subscriptions` (register Expo push token)
- `DELETE /api/v1/push-subscriptions` (deactivate Expo push token)

It now includes role-specific screen flows:

1. Sign in
2. Customer screens: `New Request` -> `Request Status`
3. Driver screens: `Offer Inbox` -> `Active Job`
4. Accept dispatch offers via `POST /api/v1/waste-requests/:id/dispatch/accept`
5. Progress status with guided actions (`accepted` -> `completed`)
6. Push live vehicle location updates
7. Live request/location updates via SSE (replacing 10s polling)
8. Foreground push-style alerts for key realtime events
9. Restore an existing auth session on app restart

## 1) Prerequisites

- Node.js 18+
- npm 9+
- Expo CLI (optional, `npx expo ...` also works)
- Running Project Divert backend API

## 2) Configure API URL

From `/Users/louisdods/Documents/GitHub/projectdivert/mobile-app`:

```bash
cp .env.example .env
```

Set `EXPO_PUBLIC_API_BASE_URL` in `.env`:

- iOS simulator on same machine: `http://127.0.0.1:5000`
- Android emulator: `http://10.0.2.2:5000`
- Physical device: `http://<your-mac-lan-ip>:5000`

Payment feature flag (recommended while still building):

- `EXPO_PUBLIC_PAYMENTS_ENABLED=0` to keep payment actions disabled in the app
- switch to `1` only when backend `PAYMENTS_ENABLED=1` and Stripe is configured

## 3) Run

```bash
npm install
npm run typecheck
npm run start
```

Then open in iOS/Android simulator or Expo Go.

## Notes

- Auth sessions are persisted with `expo-secure-store` and restored on launch.
- Realtime delivery is now SSE-based. For production with multiple API workers, route sticky sessions or a shared event bus is recommended.
- For OS background push, install Expo modules in `mobile-app`:
  - `npx expo install expo-notifications expo-device expo-constants`
  - Also configure credentials/build profiles for APNS/FCM in your Expo project.
