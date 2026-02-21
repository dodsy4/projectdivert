# Project Divert Mobile App (MVP Scaffold)

This mobile app scaffold connects directly to your existing backend APIs:

- `POST /api/v1/auth/login`
- `POST /api/v1/waste-requests`
- `GET /api/v1/waste-requests/:id`
- `GET /api/v1/waste-requests/:id/location/latest`
- `POST /api/v1/waste-requests/:id/status` (driver/admin simulation)
- `POST /api/v1/waste-requests/:id/location` (driver/admin simulation)

It includes a minimal end-to-end flow:

1. Sign in
2. Create a waste removal request (customer/admin)
3. View matched provider + drive time
4. Simulate driver status/location updates (driver/admin)
5. Poll for live status/location updates every 10 seconds

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

## 3) Run

```bash
npm install
npm run typecheck
npm run start
```

Then open in iOS/Android simulator or Expo Go.

## Notes

- This is intentionally minimal and stateful in-memory.
- Tokens are currently held in app state only.
- Next iteration should add navigation, secure token storage, and WebSocket live updates.
