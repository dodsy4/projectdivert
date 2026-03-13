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

export type ComplianceDocumentType =
  | 'carrier_license'
  | 'insurance_certificate'
  | 'waste_transfer_note'
  | 'proof_of_collection_photo';

export type ComplianceDocumentStatus = 'submitted' | 'verified' | 'rejected' | 'expired';

export type ComplianceDocument = {
  id: number;
  waste_removal_request_id: number;
  uploaded_by_user_id?: number | null;
  verified_by_user_id?: number | null;
  document_type: ComplianceDocumentType | string;
  status: ComplianceDocumentStatus | string;
  file_url: string;
  document_reference?: string | null;
  issued_at?: string | null;
  expires_at?: string | null;
  verified_at?: string | null;
  notes?: string | null;
  metadata?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ComplianceSummaryEntry = {
  present: boolean;
  count: number;
  latest_status?: string | null;
  latest_document_id?: number | null;
  latest_expires_at?: string | null;
  verified: boolean;
  expired?: boolean;
};

export type ComplianceSummary = {
  required_document_types: string[];
  completion_required_document_types?: string[];
  is_ready: boolean;
  can_complete_request?: boolean;
  by_type: Record<string, ComplianceSummaryEntry>;
  total_documents: number;
};

export type DispatchComplianceSummary = {
  required_document_types: string[];
  dispatch_required_document_types: string[];
  dispatch_eligible: boolean;
  dispatch_missing_document_types: string[];
  by_type: Record<string, ComplianceSummaryEntry>;
  total_documents: number;
};

export type CarrierCompany = {
  id: number;
  name: string;
  contact_email?: string | null;
  contact_phone?: string | null;
  is_active: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  compliance?: DispatchComplianceSummary;
};

export type DispatchEligibilitySummary = {
  driver: DispatchComplianceSummary;
  company: DispatchComplianceSummary | null;
  carrier_company_assigned: boolean;
  carrier_company_active: boolean;
  carrier_company: CarrierCompany | null;
};

export type DispatchDriver = {
  id: number;
  email: string;
  name?: string | null;
  role: string;
  is_active: boolean;
  carrier_company_id?: number | null;
  carrier_company?: CarrierCompany | null;
  dispatch_eligible: boolean;
  dispatch_missing_document_types: string[];
  compliance: DispatchEligibilitySummary;
};

export type RequestComplianceDetails = {
  request_id: number;
  request_status: string;
  documents: ComplianceDocument[];
  summary: ComplianceSummary;
};

export type DriverComplianceDocumentRecord = Omit<ComplianceDocument, 'waste_removal_request_id'> & {
  driver_user_id: number;
};

export type DriverOwnComplianceResponse = {
  driver: DispatchDriver;
  documents: DriverComplianceDocumentRecord[];
  summary: DispatchComplianceSummary;
};

export type AdminDriversResponse = {
  items: DispatchDriver[];
  pagination: {
    limit: number;
    offset: number;
    returned: number;
    total: number;
    has_more: boolean;
  };
  filters: {
    active?: boolean | string | null;
    search?: string;
  };
};

export type CreateComplianceDocumentPayload = {
  document_type: ComplianceDocumentType | string;
  file_url: string;
  document_reference?: string;
  notes?: string;
  issued_at?: string;
  expires_at?: string;
  metadata?: Record<string, unknown>;
};

export type ReviewComplianceDocumentPayload = {
  status: 'verified' | 'rejected' | 'expired';
  notes?: string;
  expires_at?: string;
  metadata?: Record<string, unknown>;
};

export type UploadComplianceFilePayload = {
  document_type: ComplianceDocumentType | string;
  uri: string;
  file_name?: string;
  mime_type?: string;
};

export type UploadComplianceFileResponse = {
  request_id: number;
  document_type: string;
  upload: {
    backend?: string;
    file_url: string;
    storage_key?: string | null;
    static_path?: string | null;
    original_filename: string;
    content_type?: string | null;
    size_bytes: number;
  };
};

export type CreateSignedComplianceUploadPayload = {
  document_type: ComplianceDocumentType | string;
  file_name: string;
  mime_type: string;
};

export type SignedComplianceUploadResponse = {
  request_id: number;
  document_type: string;
  backend: string;
  method: 'PUT' | string;
  upload_url: string;
  headers: Record<string, string>;
  expires_in_seconds: number;
  upload: UploadComplianceFileResponse['upload'];
};

export type PaymentCharge = {
  id: number;
  waste_removal_request_id: number;
  customer_user_id?: number | null;
  processor?: string | null;
  payment_intent_id?: string | null;
  charge_id?: string | null;
  amount_minor: number;
  currency: string;
  platform_fee_minor: number;
  driver_payout_minor: number;
  status: string;
  client_secret?: string | null;
  last_error?: string | null;
  paid_at?: string | null;
  refunded_at?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
};

export type PaymentRefund = {
  id: number;
  waste_removal_request_id: number;
  payment_charge_id: number;
  processor?: string | null;
  refund_id?: string | null;
  amount_minor: number;
  currency: string;
  status: string;
  reason?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type DriverPayout = {
  id: number;
  waste_removal_request_id: number;
  payment_charge_id: number;
  driver_user_id: number;
  processor?: string | null;
  payout_id?: string | null;
  destination_account_id?: string | null;
  amount_minor: number;
  currency: string;
  status: string;
  paid_out_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type RequestFinancials = {
  charges: PaymentCharge[];
  refunds: PaymentRefund[];
  payouts: DriverPayout[];
  totals: {
    charged_minor: number;
    refunded_minor: number;
    paid_out_minor: number;
    platform_net_minor: number;
  };
};

export type BillingSummary = {
  mode: 'offline' | 'in_app' | string;
  payments_enabled: boolean;
  stripe_configured?: boolean;
  launch_scope?: string;
  offline_reason?: string | null;
  customer_message?: string;
  admin_message?: string;
  actions_disabled?: string[];
};

export type BillingWorkflowState =
  | 'pending_offline_invoice'
  | 'invoice_sent'
  | 'paid_offline'
  | 'payout_recorded'
  | 'cancelled';

export type BillingWorkflow = {
  state: BillingWorkflowState | string;
  reference?: string | null;
  notes?: string | null;
  updated_at?: string | null;
  updated_by_user_id?: number | null;
};

export type BillingFollowupWorkflowState = 'open' | 'acknowledged' | 'closed';

export type BillingFollowupWorkflow = {
  state: BillingFollowupWorkflowState | string;
  notes?: string | null;
  updated_at?: string | null;
  updated_by_user_id?: number | null;
  active?: boolean;
};

export type RequestCommunicationDirection = 'outbound' | 'inbound' | 'internal';
export type RequestCommunicationChannel = 'email' | 'phone' | 'sms' | 'manual' | 'other';

export type RequestCommunicationLog = {
  id: number;
  waste_removal_request_id: number;
  created_by_user_id?: number | null;
  direction: RequestCommunicationDirection | string;
  channel: RequestCommunicationChannel | string;
  subject?: string | null;
  message: string;
  outcome?: string | null;
  contact_name?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
  customer_visible: boolean;
  occurred_at?: string | null;
  created_at?: string | null;
};

export type RequestCommunicationSummary = {
  total: number;
  customer_visible_count: number;
  direction_counts: Record<string, number>;
  channel_counts: Record<string, number>;
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
  billing_workflow?: BillingWorkflow | null;
  billing_followup_workflow?: BillingFollowupWorkflow | null;
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
  financials?: RequestFinancials;
  billing?: BillingSummary;
  communications?: RequestCommunicationLog[];
  communication_summary?: RequestCommunicationSummary;
  compliance?: {
    documents: ComplianceDocument[];
    summary: ComplianceSummary;
  };
};

export type WasteRequestFinancialsResponse = {
  request_id: number;
  request_status: string;
  payments_enabled: boolean;
  billing: BillingSummary;
  financials: RequestFinancials;
};

export type UpdateBillingWorkflowPayload = {
  state: BillingWorkflowState | string;
  reference?: string;
  notes?: string;
};

export type UpdateBillingWorkflowResponse = {
  updated: boolean;
  previous_state?: string;
  request: WasteRequest;
  billing: BillingSummary;
  financials: RequestFinancials;
};

export type AdminBillingQueueItem = {
  request: WasteRequest;
  billing: BillingSummary;
  financials: RequestFinancials;
};

export type AdminBillingQueueResponse = {
  items: AdminBillingQueueItem[];
  pagination: {
    limit: number;
    offset: number;
    returned: number;
    total: number;
    has_more: boolean;
  };
  filters: {
    state: string;
    request_status: string;
    reference: string;
    search: string;
  };
  summary: {
    state_counts: Record<string, number>;
  };
};

export type BillingFollowup = {
  workflow?: BillingFollowupWorkflow | null;
  due_now: boolean;
  due_reason?: string | null;
  suppressed_reason?: string | null;
  reminder_after_hours: number;
  repeat_hours: number;
  invoice_age_hours: number;
  hours_since_last_customer_touch?: number | null;
  hours_since_last_reminder?: number | null;
  last_customer_touch?: RequestCommunicationLog | null;
  last_reminder?: RequestCommunicationLog | null;
  recommended_template?: CommunicationTemplate | null;
};

export type AdminBillingFollowupItem = {
  request: WasteRequest;
  followup: BillingFollowup;
};

export type AdminBillingFollowupsResponse = {
  items: AdminBillingFollowupItem[];
  summary: {
    scanned: number;
    invoice_sent_candidates: number;
    due_now_count: number;
    oldest_due_hours: number;
    oldest_invoice_age_hours: number;
    suppressed_count?: number;
    state_counts?: Record<string, number>;
  };
  filters: {
    search: string;
    due_only: boolean;
    reminder_after_hours: number;
    repeat_hours: number;
    limit: number;
  };
};

export type RunBillingFollowupMaintenancePayload = {
  search?: string;
  reminder_after_hours?: number;
  repeat_hours?: number;
  limit?: number;
  dry_run?: boolean;
  log_reminders?: boolean;
};

export type UpdateBillingFollowupPayload = {
  state: BillingFollowupWorkflowState | string;
  notes?: string;
};

export type UpdateBillingFollowupResponse = {
  updated: boolean;
  previous_state: string;
  request: WasteRequest;
  followup: BillingFollowupWorkflow | null;
  communication?: RequestCommunicationLog | null;
};

export type BillingFollowupMaintenanceResponse = {
  executed_at: string;
  dry_run: boolean;
  options: {
    search: string;
    reminder_after_hours: number;
    repeat_hours: number;
    limit: number;
    log_reminders: boolean;
  };
  summary: {
    scanned: number;
    invoice_sent_candidates: number;
    due_now_count: number;
    reminders_planned: number;
    reminders_logged: number;
    changed_request_count: number;
    oldest_due_hours: number;
  };
  items: Array<{
    request_id: number;
    billing_reference?: string | null;
    billing_state: string;
    followup_state: string;
    invoice_age_hours?: number | null;
    hours_since_last_customer_touch?: number | null;
    hours_since_last_reminder?: number | null;
    due_reason?: string | null;
    suppressed_reason?: string | null;
    planned_actions: string[];
    applied_actions: string[];
  }>;
};

export type CreateRequestCommunicationPayload = {
  direction: RequestCommunicationDirection | string;
  channel: RequestCommunicationChannel | string;
  subject?: string;
  message: string;
  outcome?: string;
  contact_name?: string;
  contact_email?: string;
  contact_phone?: string;
  customer_visible?: boolean;
  occurred_at?: string;
};

export type RequestCommunicationsResponse = {
  request_id: number;
  communications: RequestCommunicationLog[];
  summary: RequestCommunicationSummary;
  filters: {
    customer_visible_only: boolean;
    limit: number;
  };
};

export type CreateRequestCommunicationResponse = {
  created: boolean;
  communication: RequestCommunicationLog;
  communications: RequestCommunicationLog[];
  summary: RequestCommunicationSummary;
  request: WasteRequestDetails;
};

export type CommunicationTemplate = {
  key: string;
  label: string;
  direction: RequestCommunicationDirection | string;
  channel: RequestCommunicationChannel | string;
  customer_visible: boolean;
  outcome?: string | null;
  subject?: string | null;
  message: string;
};

export type CommunicationTemplatesResponse = {
  request_id: number;
  templates: CommunicationTemplate[];
};

export type AdminCommunicationsReportItem = {
  communication: RequestCommunicationLog;
  request: WasteRequest | null;
};

export type AdminCommunicationsReportResponse = {
  items: AdminCommunicationsReportItem[];
  pagination: {
    limit: number;
    offset: number;
    returned: number;
    total: number;
    has_more: boolean;
  };
  filters: {
    state: string;
    direction: string;
    channel: string;
    customer_visible?: boolean | null;
    search: string;
  };
  summary: {
    direction_counts: Record<string, number>;
    channel_counts: Record<string, number>;
  };
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
  | 'compliance_document_created'
  | 'compliance_document_reviewed'
  | 'admin_billing_updated'
  | 'admin_communication_logged'
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

export type ComplianceDocumentMutationResponse = {
  request_id: number;
  document: ComplianceDocument;
  summary: ComplianceSummary;
  previous_status?: string;
  updated?: boolean;
};

export type AdminComplianceReviewQueueItem = {
  document: ComplianceDocument;
  request: WasteRequest | null;
  summary: ComplianceSummary | null;
};

export type AdminComplianceReviewQueueResponse = {
  items: AdminComplianceReviewQueueItem[];
  pagination: {
    limit: number;
    offset: number;
    returned: number;
    total: number;
    has_more: boolean;
  };
  filters: {
    status: string;
    document_type: string;
  };
  summary: {
    status_counts: Record<string, number>;
    document_type_counts: Record<string, number>;
  };
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

async function requestMultipartJson<T>(
  path: string,
  formData: FormData,
  options: RequestJsonOptions = {},
): Promise<T | null> {
  const { token, allow404 = false, retryOnAuthFailure = true } = options;
  const headers: Record<string, string> = {
    Accept: 'application/json',
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${apiBaseUrl}${path}`, {
    method: 'POST',
    headers,
    body: formData,
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
        return requestMultipartJson<T>(path, formData, {
          token: refreshed.access_token,
          allow404,
          retryOnAuthFailure: false,
        });
      }
    }
    const parsed = body as { error?: string };
    const message =
      typeof parsed?.error === 'string' ? parsed.error : `Request failed (${response.status})`;
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

  getWasteRequestCompliance(requestId: number, token: string) {
    return requestJson<RequestComplianceDetails>(
      `/api/v1/waste-requests/${requestId}/compliance`,
      { method: 'GET' },
      { token },
    ) as Promise<RequestComplianceDetails>;
  },

  getWasteRequestFinancials(requestId: number, token: string) {
    return requestJson<WasteRequestFinancialsResponse>(
      `/api/v1/waste-requests/${requestId}/payments`,
      { method: 'GET' },
      { token },
    ) as Promise<WasteRequestFinancialsResponse>;
  },

  updateBillingWorkflow(requestId: number, payload: UpdateBillingWorkflowPayload, token: string) {
    return requestJson<UpdateBillingWorkflowResponse>(
      `/api/v1/admin/waste-requests/${requestId}/billing`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
      { token },
    ) as Promise<UpdateBillingWorkflowResponse>;
  },

  getDriverOwnCompliance(token: string) {
    return requestJson<DriverOwnComplianceResponse>(
      '/api/v1/drivers/me/compliance',
      { method: 'GET' },
      { token },
    ) as Promise<DriverOwnComplianceResponse>;
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

  createComplianceDocument(
    requestId: number,
    payload: CreateComplianceDocumentPayload,
    token: string,
  ) {
    return requestJson<ComplianceDocumentMutationResponse>(
      `/api/v1/waste-requests/${requestId}/compliance/documents`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
      { token },
    ) as Promise<ComplianceDocumentMutationResponse>;
  },

  uploadComplianceFile(
    requestId: number,
    payload: UploadComplianceFilePayload,
    token: string,
  ) {
    const formData = new FormData();
    formData.append('document_type', String(payload.document_type));
    formData.append(
      'file',
      {
        uri: payload.uri,
        name: payload.file_name || 'compliance-upload',
        type: payload.mime_type || 'application/octet-stream',
      } as unknown as Blob,
    );
    return requestMultipartJson<UploadComplianceFileResponse>(
      `/api/v1/waste-requests/${requestId}/compliance/uploads`,
      formData,
      { token },
    ) as Promise<UploadComplianceFileResponse>;
  },

  createSignedComplianceUpload(
    requestId: number,
    payload: CreateSignedComplianceUploadPayload,
    token: string,
  ) {
    return requestJson<SignedComplianceUploadResponse>(
      `/api/v1/waste-requests/${requestId}/compliance/uploads/sign`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
      { token },
    ) as Promise<SignedComplianceUploadResponse>;
  },

  reviewComplianceDocument(
    requestId: number,
    documentId: number,
    payload: ReviewComplianceDocumentPayload,
    token: string,
  ) {
    return requestJson<ComplianceDocumentMutationResponse>(
      `/api/v1/admin/waste-requests/${requestId}/compliance/documents/${documentId}/verify`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
      { token },
    ) as Promise<ComplianceDocumentMutationResponse>;
  },

  getAdminComplianceReviewQueue(
    token: string,
    params: { status?: string; documentType?: string; limit?: number } = {},
  ) {
    const search = new URLSearchParams();
    if (params.status) {
      search.set('status', params.status);
    }
    if (params.documentType) {
      search.set('document_type', params.documentType);
    }
    if (params.limit) {
      search.set('limit', String(params.limit));
    }
    const suffix = search.toString() ? `?${search.toString()}` : '';
    return requestJson<AdminComplianceReviewQueueResponse>(
      `/api/v1/admin/compliance/review-queue${suffix}`,
      { method: 'GET' },
      { token },
    ) as Promise<AdminComplianceReviewQueueResponse>;
  },

  getAdminDrivers(
    token: string,
    params: { active?: boolean; limit?: number; search?: string } = {},
  ) {
    const search = new URLSearchParams();
    if (params.active !== undefined) {
      search.set('active', params.active ? 'true' : 'false');
    }
    if (params.limit) {
      search.set('limit', String(params.limit));
    }
    if (params.search) {
      search.set('search', params.search);
    }
    const suffix = search.toString() ? `?${search.toString()}` : '';
    return requestJson<AdminDriversResponse>(
      `/api/v1/admin/drivers${suffix}`,
      { method: 'GET' },
      { token },
    ) as Promise<AdminDriversResponse>;
  },

  getAdminBillingQueue(
    token: string,
    params: { state?: string; requestStatus?: string; reference?: string; search?: string; limit?: number } = {},
  ) {
    const searchParams = new URLSearchParams();
    if (params.state) {
      searchParams.set('state', params.state);
    }
    if (params.requestStatus) {
      searchParams.set('request_status', params.requestStatus);
    }
    if (params.reference) {
      searchParams.set('reference', params.reference);
    }
    if (params.search) {
      searchParams.set('search', params.search);
    }
    if (params.limit) {
      searchParams.set('limit', String(params.limit));
    }
    const suffix = searchParams.toString() ? `?${searchParams.toString()}` : '';
    return requestJson<AdminBillingQueueResponse>(
      `/api/v1/admin/billing/requests${suffix}`,
      { method: 'GET' },
      { token },
    ) as Promise<AdminBillingQueueResponse>;
  },

  getAdminBillingFollowups(
    token: string,
    params: {
      search?: string;
      dueOnly?: boolean;
      reminderAfterHours?: number;
      repeatHours?: number;
      limit?: number;
    } = {},
  ) {
    const searchParams = new URLSearchParams();
    if (params.search) {
      searchParams.set('search', params.search);
    }
    if (params.dueOnly !== undefined) {
      searchParams.set('due_only', params.dueOnly ? 'true' : 'false');
    }
    if (params.reminderAfterHours !== undefined) {
      searchParams.set('reminder_after_hours', String(params.reminderAfterHours));
    }
    if (params.repeatHours !== undefined) {
      searchParams.set('repeat_hours', String(params.repeatHours));
    }
    if (params.limit) {
      searchParams.set('limit', String(params.limit));
    }
    const suffix = searchParams.toString() ? `?${searchParams.toString()}` : '';
    return requestJson<AdminBillingFollowupsResponse>(
      `/api/v1/admin/billing/followups${suffix}`,
      { method: 'GET' },
      { token },
    ) as Promise<AdminBillingFollowupsResponse>;
  },

  runAdminBillingFollowupMaintenance(
    token: string,
    payload: RunBillingFollowupMaintenancePayload,
  ) {
    return requestJson<BillingFollowupMaintenanceResponse>(
      '/api/v1/admin/billing/followups/maintenance',
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
      { token },
    ) as Promise<BillingFollowupMaintenanceResponse>;
  },

  updateBillingFollowup(
    requestId: number,
    payload: UpdateBillingFollowupPayload,
    token: string,
  ) {
    return requestJson<UpdateBillingFollowupResponse>(
      `/api/v1/admin/waste-requests/${requestId}/billing-followup`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
      { token },
    ) as Promise<UpdateBillingFollowupResponse>;
  },

  getWasteRequestCommunications(requestId: number, token: string, limit = 50) {
    return requestJson<RequestCommunicationsResponse>(
      `/api/v1/waste-requests/${requestId}/communications?limit=${limit}`,
      { method: 'GET' },
      { token },
    ) as Promise<RequestCommunicationsResponse>;
  },

  createWasteRequestCommunication(
    requestId: number,
    payload: CreateRequestCommunicationPayload,
    token: string,
  ) {
    return requestJson<CreateRequestCommunicationResponse>(
      `/api/v1/admin/waste-requests/${requestId}/communications`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
      { token },
    ) as Promise<CreateRequestCommunicationResponse>;
  },

  getWasteRequestCommunicationTemplates(requestId: number, token: string) {
    return requestJson<CommunicationTemplatesResponse>(
      `/api/v1/admin/waste-requests/${requestId}/communications/templates`,
      { method: 'GET' },
      { token },
    ) as Promise<CommunicationTemplatesResponse>;
  },

  getAdminCommunicationsReport(
    token: string,
    params: {
      state?: string;
      direction?: string;
      channel?: string;
      customerVisible?: boolean;
      search?: string;
      limit?: number;
    } = {},
  ) {
    const searchParams = new URLSearchParams();
    if (params.state) {
      searchParams.set('state', params.state);
    }
    if (params.direction) {
      searchParams.set('direction', params.direction);
    }
    if (params.channel) {
      searchParams.set('channel', params.channel);
    }
    if (params.customerVisible !== undefined) {
      searchParams.set('customer_visible', params.customerVisible ? 'true' : 'false');
    }
    if (params.search) {
      searchParams.set('search', params.search);
    }
    if (params.limit) {
      searchParams.set('limit', String(params.limit));
    }
    const suffix = searchParams.toString() ? `?${searchParams.toString()}` : '';
    return requestJson<AdminCommunicationsReportResponse>(
      `/api/v1/admin/communications/report${suffix}`,
      { method: 'GET' },
      { token },
    ) as Promise<AdminCommunicationsReportResponse>;
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
