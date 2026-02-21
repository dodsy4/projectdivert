declare const process: { env: Record<string, string | undefined> };

export type UserRole = 'customer' | 'driver' | 'admin';

export type AuthResponse = {
  access_token: string;
  token_type: string;
  expires_in_hours: number;
  user: {
    id: number;
    email: string;
    name: string;
    role: UserRole;
  };
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
};

export type DriveTime = {
  distance_text?: string;
  duration_text?: string;
  duration_minutes?: number;
  status?: string;
};

export type CreateWasteRequestResponse = {
  request: WasteRequest;
  match: WasteMatch | null;
  drive_time: DriveTime | null;
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

async function requestJson<T>(
  path: string,
  init: RequestInit,
  token?: string,
  allow404 = false,
): Promise<T | null> {
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
    const parsed = body as { error?: string };
    const message = typeof parsed?.error === 'string' ? parsed.error : `Request failed (${response.status})`;
    throw new ApiError(message, response.status, body);
  }

  return body as T;
}

export const apiClient = {
  apiBaseUrl,

  login(email: string, password: string) {
    return requestJson<AuthResponse>(
      '/api/v1/auth/login',
      {
        method: 'POST',
        body: JSON.stringify({ email, password }),
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
      token,
    ) as Promise<CreateWasteRequestResponse>;
  },

  getWasteRequest(requestId: number, token: string) {
    return requestJson<WasteRequestDetails>(`/api/v1/waste-requests/${requestId}`, { method: 'GET' }, token) as Promise<WasteRequestDetails>;
  },

  getLatestLocation(requestId: number, token: string) {
    return requestJson<{ request_id: number; request_status: string; latest_location: VehicleLocation }>(
      `/api/v1/waste-requests/${requestId}/location/latest`,
      { method: 'GET' },
      token,
      true,
    ) as Promise<{ request_id: number; request_status: string; latest_location: VehicleLocation } | null>;
  },

  updateWasteRequestStatus(requestId: number, payload: UpdateStatusPayload, token: string) {
    return requestJson<{ request: WasteRequest }>(
      `/api/v1/waste-requests/${requestId}/status`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
      token,
    ) as Promise<{ request: WasteRequest }>;
  },

  pushVehicleLocation(requestId: number, payload: CreateLocationPayload, token: string) {
    return requestJson<{ location: VehicleLocation }>(
      `/api/v1/waste-requests/${requestId}/location`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
      token,
    ) as Promise<{ location: VehicleLocation }>;
  },
};
