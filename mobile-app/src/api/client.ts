declare const process: { env: Record<string, string | undefined> };

export type UserRole = 'customer' | 'driver' | 'admin';

export type AuthUser = {
  id: number;
  email: string;
  name: string;
  role: UserRole;
  is_active?: boolean;
  email_verified?: boolean;
  email_verified_at?: string | null;
};

export type AuthResponse = {
  access_token: string;
  refresh_token?: string;
  token_type: string;
  expires_in_hours: number;
  refresh_expires_in_days?: number;
  user: AuthUser;
};

export type SignupResponse =
  | (AuthResponse & {
      created?: boolean;
    })
  | {
      created: boolean;
      verification_required: true;
      verification_email_sent: boolean;
      verification_token?: string;
      user: AuthUser;
    };

export type VerifyRequestResponse = {
  message: string;
  verification_email_sent?: boolean;
  verification_token?: string;
};

export type PasswordResetRequestResponse = {
  message: string;
  reset_email_sent?: boolean;
  reset_token?: string;
};

export type CreateWasteRequestPayload = {
  requester_name: string;
  requester_email: string;
  material_type: string;
  custom_material_type?: string;
  waste_amount: number;
  waste_unit: string;
  match_radius_miles: number;
  pickup_address: string;
  pickup_city?: string;
  pickup_county?: string;
  pickup_postcode: string;
  scheduled_pickup_at: string;
  notes?: string;
};

export type UpdateStatusPayload = {
  status:
    | 'pending_match'
    | 'matched'
    | 'accepted'
    | 'rejected'
    | 'en_route'
    | 'arrived'
    | 'collected'
    | 'completed'
    | 'cancelled';
};

export type CreateLocationPayload = {
  latitude: number;
  longitude: number;
  driver_id?: string;
  vehicle_id?: string;
  recorded_at?: string;
  source?: string;
};

export type WasteRequest = {
  id: number;
  requester_name: string;
  requester_email: string;
  material_type: string;
  waste_amount: number;
  waste_unit: string;
  pickup_address: string;
  pickup_city?: string | null;
  pickup_county?: string | null;
  pickup_postcode: string;
  scheduled_pickup_at: string;
  notes?: string | null;
  status: string;
  assigned_driver_user_id?: number | null;
  created_at: string;
};

export type WasteMatch = {
  id: number;
  waste_removal_request_id: number;
  provider_name: string;
  provider_type?: string | null;
  provider_city?: string | null;
  provider_postcode?: string | null;
  provider_latitude: number;
  provider_longitude: number;
  distance_miles: number;
  match_radius_miles: number;
  created_at: string;
};

export type VehicleLocation = {
  id: number;
  waste_removal_request_id: number;
  driver_id?: string | null;
  vehicle_id?: string | null;
  latitude: number;
  longitude: number;
  recorded_at: string;
  source: string;
  created_at: string;
};

export type WasteRequestDetails = {
  request: WasteRequest;
  match: WasteMatch | null;
  latest_location: VehicleLocation | null;
  dispatch?: DispatchSummary;
};

export type WasteRequestRealtimeEventName =
  | 'snapshot'
  | 'request_created'
  | 'dispatch_offer_accepted'
  | 'status_updated'
  | 'location_updated'
  | 'payment_succeeded'
  | 'refund_processed'
  | 'payout_processed'
  | 'admin_dispatch_override'
  | 'admin_dispatch_incident_ack'
  | 'admin_dispatch_incident_resolve'
  | 'admin_dispatch_incident_owner_reassign';

export type WasteRequestRealtimeEvent = {
  event_id?: number | string;
  event: WasteRequestRealtimeEventName;
  request_id: number;
  occurred_at: string;
  payload: WasteRequestDetails | null;
  metadata?: Record<string, unknown>;
};

export type DriveTime = {
  minutes?: number;
  text?: string;
};

export type DispatchCandidate = {
  provider_name: string;
  provider_type?: string | null;
  provider_city?: string | null;
  provider_postcode?: string | null;
  provider_latitude: number;
  provider_longitude: number;
  provider_email?: string | null;
  provider_phone?: string | null;
  distance_miles: number;
};

export type DispatchOffer = {
  id: number;
  waste_removal_request_id: number;
  provider_name: string;
  provider_type?: string | null;
  provider_city?: string | null;
  provider_postcode?: string | null;
  provider_latitude: number;
  provider_longitude: number;
  provider_email?: string | null;
  provider_phone?: string | null;
  distance_miles: number;
  match_radius_miles: number;
  offer_rank: number;
  status: string;
  notified_at: string;
  responded_at?: string | null;
  created_at: string;
};

export type DispatchSummary = {
  offers_sent: number;
  offers_open: number;
  accepted_offer: DispatchOffer | null;
};

export type CreateWasteRequestResponse = {
  request: WasteRequest;
  match: WasteMatch | null;
  drive_time: DriveTime | null;
  dispatch?: {
    offers_created: number;
    provider_notifications_sent: number;
    closest_candidate: DispatchCandidate | null;
  };
};

export type AcceptDispatchOfferPayload = {
  offer_token: string;
};

export type AcceptDispatchOfferResponse = {
  request: WasteRequest;
  match: WasteMatch;
  accepted_offer: DispatchOffer;
  dispatch: DispatchSummary;
};

export type UpsertPushSubscriptionPayload = {
  token: string;
  provider?: 'expo';
  platform?: string;
};

export type DeletePushSubscriptionPayload = {
  token: string;
};

export class ApiError extends Error {
  status: number;
  details: unknown;

  constructor(message: string, status: number, details: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.details = details;
  }
}

const apiBaseUrl =
  (process.env.EXPO_PUBLIC_API_BASE_URL || '').trim().replace(/\/+$/, '') ||
  'http://127.0.0.1:5000';

const paymentsEnabled = ['1', 'true', 'yes', 'on'].includes(
  (process.env.EXPO_PUBLIC_PAYMENTS_ENABLED || '0').trim().toLowerCase(),
);
const realtimeReconnectDelayMs = Number.parseInt(
  (process.env.EXPO_PUBLIC_REALTIME_RECONNECT_DELAY_MS || '2500').trim(),
  10,
);
const realtimeFallbackPollIntervalMs = Number.parseInt(
  (process.env.EXPO_PUBLIC_REALTIME_POLL_FALLBACK_INTERVAL_MS || '10000').trim(),
  10,
);
const normalizedRealtimeReconnectDelayMs = Number.isFinite(realtimeReconnectDelayMs) && realtimeReconnectDelayMs > 0
  ? realtimeReconnectDelayMs
  : 2500;
const normalizedRealtimeFallbackPollIntervalMs = Number.isFinite(realtimeFallbackPollIntervalMs) && realtimeFallbackPollIntervalMs > 0
  ? realtimeFallbackPollIntervalMs
  : 10000;

type StreamWasteRequestEventsOptions = {
  signal?: AbortSignal;
  onOpen?: () => void;
  onEvent: (event: WasteRequestRealtimeEvent) => void;
  lastEventId?: string | null;
};

type RequestJsonOptions = {
  token?: string;
  allow404?: boolean;
  retryOnAuthFailure?: boolean;
};

type AuthLifecycleHooks = {
  getAuth: () => AuthResponse | null;
  onAuthRefreshed: (auth: AuthResponse) => void | Promise<void>;
  onAuthInvalid: () => void | Promise<void>;
};

let authLifecycleHooks: AuthLifecycleHooks | null = null;
let refreshInFlight: Promise<AuthResponse | null> | null = null;

function setAuthLifecycleHooks(hooks: AuthLifecycleHooks | null) {
  authLifecycleHooks = hooks;
}

function parseSseFrame(frame: string): { event: string; data: string; id: string | null } | null {
  const lines = frame.replace(/\r/g, '').split('\n');
  let eventName = 'message';
  let eventId: string | null = null;
  const dataLines: string[] = [];

  for (const line of lines) {
    if (!line || line.startsWith(':')) {
      continue;
    }
    if (line.startsWith('event:')) {
      eventName = line.slice('event:'.length).trim() || 'message';
      continue;
    }
    if (line.startsWith('id:')) {
      const parsed = line.slice('id:'.length).trim();
      eventId = parsed || null;
      continue;
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).trimStart());
    }
  }

  if (!dataLines.length) {
    return null;
  }
  return {
    event: eventName,
    data: dataLines.join('\n'),
    id: eventId,
  };
}

async function requestJson<T>(
  path: string,
  init: RequestInit,
  options: RequestJsonOptions = {},
): Promise<T | null> {
  const { token, allow404 = false, retryOnAuthFailure = true } = options;
  const headers: Record<string, string> = {
    Accept: 'application/json',
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> | undefined),
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers,
  });

  const text = await response.text();
  let body: unknown = {};
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = { raw: text };
    }
  }

  if (!response.ok) {
    if (allow404 && response.status === 404) {
      return null;
    }
    if (response.status === 401 && token && retryOnAuthFailure) {
      const refreshed = await runRefreshFlow();
      if (refreshed?.access_token) {
        return requestJson<T>(path, init, {
          token: refreshed.access_token,
          allow404,
          retryOnAuthFailure: false,
        });
      }
    }
    const parsed = body as { error?: string };
    const message = typeof parsed?.error === 'string' ? parsed.error : `Request failed (${response.status})`;
    throw new ApiError(message, response.status, body);
  }

  return body as T;
}

async function runRefreshFlow(): Promise<AuthResponse | null> {
  if (!authLifecycleHooks) {
    return null;
  }

  if (refreshInFlight) {
    return refreshInFlight;
  }

  refreshInFlight = (async () => {
    const hooks = authLifecycleHooks;
    const currentAuth = hooks?.getAuth();
    const refreshToken = (currentAuth?.refresh_token || '').trim();
    if (!hooks || !refreshToken) {
      return null;
    }

    try {
      const refreshed = (await requestJson<AuthResponse>(
        '/api/v1/auth/refresh',
        {
          method: 'POST',
          body: JSON.stringify({ refresh_token: refreshToken }),
        },
        {
          retryOnAuthFailure: false,
        },
      )) as AuthResponse;
      await hooks.onAuthRefreshed(refreshed);
      return refreshed;
    } catch (err) {
      if (err instanceof ApiError && (err.status === 400 || err.status === 401 || err.status === 403)) {
        await hooks.onAuthInvalid();
        return null;
      }
      throw err;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

export const apiClient = {
  apiBaseUrl,
  paymentsEnabled,
  realtimeReconnectDelayMs: normalizedRealtimeReconnectDelayMs,
  realtimeFallbackPollIntervalMs: normalizedRealtimeFallbackPollIntervalMs,

  configureAuthLifecycle(hooks: AuthLifecycleHooks | null) {
    setAuthLifecycleHooks(hooks);
  },

  login(email: string, password: string) {
    return requestJson<AuthResponse>(
      '/api/v1/auth/login',
      {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      },
    ) as Promise<AuthResponse>;
  },

  signup(payload: { name: string; email: string; password: string }) {
    return requestJson<SignupResponse>(
      '/api/v1/auth/signup',
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    ) as Promise<SignupResponse>;
  },

  refresh(refreshToken: string) {
    return requestJson<AuthResponse>(
      '/api/v1/auth/refresh',
      {
        method: 'POST',
        body: JSON.stringify({ refresh_token: refreshToken }),
      },
      {
        retryOnAuthFailure: false,
      },
    ) as Promise<AuthResponse>;
  },

  logout(refreshToken: string, accessToken?: string) {
    return requestJson<{ revoked: boolean; message?: string }>(
      '/api/v1/auth/logout',
      {
        method: 'POST',
        body: JSON.stringify({ refresh_token: refreshToken }),
      },
      {
        token: accessToken,
        retryOnAuthFailure: false,
      },
    ) as Promise<{ revoked: boolean; message?: string }>;
  },

  requestEmailVerification(email: string) {
    return requestJson<VerifyRequestResponse>(
      '/api/v1/auth/verify/request',
      {
        method: 'POST',
        body: JSON.stringify({ email }),
      },
      {
        retryOnAuthFailure: false,
      },
    ) as Promise<VerifyRequestResponse>;
  },

  confirmEmailVerification(token: string) {
    return requestJson<AuthResponse>(
      '/api/v1/auth/verify/confirm',
      {
        method: 'POST',
        body: JSON.stringify({ token }),
      },
      {
        retryOnAuthFailure: false,
      },
    ) as Promise<AuthResponse>;
  },

  requestPasswordReset(email: string) {
    return requestJson<PasswordResetRequestResponse>(
      '/api/v1/auth/password-reset/request',
      {
        method: 'POST',
        body: JSON.stringify({ email }),
      },
      {
        retryOnAuthFailure: false,
      },
    ) as Promise<PasswordResetRequestResponse>;
  },

  confirmPasswordReset(token: string, newPassword: string) {
    return requestJson<AuthResponse>(
      '/api/v1/auth/password-reset/confirm',
      {
        method: 'POST',
        body: JSON.stringify({ token, new_password: newPassword }),
      },
      {
        retryOnAuthFailure: false,
      },
    ) as Promise<AuthResponse>;
  },

  createWasteRequest(payload: CreateWasteRequestPayload, token: string) {
    return requestJson<CreateWasteRequestResponse>(
      '/api/v1/waste-requests',
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
      { token },
    ) as Promise<CreateWasteRequestResponse>;
  },

  getWasteRequest(requestId: number, token: string) {
    return requestJson<WasteRequestDetails>(`/api/v1/waste-requests/${requestId}`, { method: 'GET' }, { token }) as Promise<WasteRequestDetails>;
  },

  getLatestLocation(requestId: number, token: string) {
    return requestJson<{ request_id: number; request_status: string; latest_location: VehicleLocation }>(
      `/api/v1/waste-requests/${requestId}/location/latest`,
      { method: 'GET' },
      {
        token,
        allow404: true,
      },
    ) as Promise<{ request_id: number; request_status: string; latest_location: VehicleLocation } | null>;
  },

  updateWasteRequestStatus(requestId: number, payload: UpdateStatusPayload, token: string) {
    return requestJson<{ request: WasteRequest }>(
      `/api/v1/waste-requests/${requestId}/status`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
      { token },
    ) as Promise<{ request: WasteRequest }>;
  },

  pushVehicleLocation(requestId: number, payload: CreateLocationPayload, token: string) {
    return requestJson<{ location: VehicleLocation }>(
      `/api/v1/waste-requests/${requestId}/location`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
      { token },
    ) as Promise<{ location: VehicleLocation }>;
  },

  acceptDispatchOffer(requestId: number, payload: AcceptDispatchOfferPayload, token: string) {
    return requestJson<AcceptDispatchOfferResponse>(
      `/api/v1/waste-requests/${requestId}/dispatch/accept`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
      { token },
    ) as Promise<AcceptDispatchOfferResponse>;
  },

  upsertPushSubscription(payload: UpsertPushSubscriptionPayload, token: string) {
    return requestJson<{ subscription: Record<string, unknown> }>(
      '/api/v1/push-subscriptions',
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
      { token },
    ) as Promise<{ subscription: Record<string, unknown> }>;
  },

  deletePushSubscription(payload: DeletePushSubscriptionPayload, token: string) {
    return requestJson<{ deactivated: boolean }>(
      '/api/v1/push-subscriptions',
      {
        method: 'DELETE',
        body: JSON.stringify(payload),
      },
      { token },
    ) as Promise<{ deactivated: boolean }>;
  },

  async streamWasteRequestEvents(
    requestId: number,
    token: string,
    options: StreamWasteRequestEventsOptions,
  ): Promise<void> {
    const encodedLastEventId = options.lastEventId
      ? encodeURIComponent(options.lastEventId)
      : '';
    const querySuffix = encodedLastEventId ? `?last_event_id=${encodedLastEventId}` : '';

    const openStream = (accessToken: string) =>
      fetch(`${apiBaseUrl}/api/v1/waste-requests/${requestId}/events${querySuffix}`, {
        method: 'GET',
        headers: {
          Accept: 'text/event-stream',
          Authorization: `Bearer ${accessToken}`,
          ...(options.lastEventId ? { 'Last-Event-ID': options.lastEventId } : {}),
        },
        signal: options.signal,
      });

    let response = await openStream(token);
    if (response.status === 401) {
      const refreshed = await runRefreshFlow();
      if (refreshed?.access_token) {
        response = await openStream(refreshed.access_token);
      }
    }

    if (!response.ok) {
      const raw = await response.text();
      let details: unknown = {};
      try {
        details = raw ? JSON.parse(raw) : {};
      } catch {
        details = { raw };
      }
      const parsed = details as { error?: string };
      const message =
        typeof parsed?.error === 'string'
          ? parsed.error
          : `Realtime stream failed (${response.status})`;
      throw new ApiError(message, response.status, details);
    }

    if (!response.body) {
      throw new Error('Realtime stream is unavailable in this runtime.');
    }

    options.onOpen?.();

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        return;
      }

      buffer += decoder.decode(value, { stream: true });
      while (true) {
        const frameBoundary = buffer.indexOf('\n\n');
        if (frameBoundary < 0) {
          break;
        }

        const frame = buffer.slice(0, frameBoundary);
        buffer = buffer.slice(frameBoundary + 2);
        const parsed = parseSseFrame(frame);
        if (!parsed || parsed.event !== 'waste_request') {
          continue;
        }

        try {
          const payload = JSON.parse(parsed.data) as WasteRequestRealtimeEvent;
          if (parsed.id && payload.event_id === undefined) {
            const numericId = Number.parseInt(parsed.id, 10);
            payload.event_id = Number.isFinite(numericId) ? numericId : parsed.id;
          }
          options.onEvent(payload);
        } catch {
          // Ignore malformed frames to keep stream alive.
        }
      }
    }
  },
};
