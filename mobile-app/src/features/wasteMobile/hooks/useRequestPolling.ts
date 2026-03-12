import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type {
  AuthResponse,
  WasteRequestDetails,
  WasteRequestRealtimeEvent,
} from '../../../api/client';
import { apiClient } from '../../../api/client';
import type { AdminViewMode } from '../types';
import { normalizeError } from './utils';

type UseRequestPollingParams = {
  auth: AuthResponse | null;
  adminViewMode: AdminViewMode;
  customerRequestIdParsed: number | null;
  driverJobRequestIdParsed: number | null;
  setError: React.Dispatch<React.SetStateAction<string | null>>;
  onRealtimeEvent?: (event: WasteRequestRealtimeEvent) => void;
};

type RealtimeSyncState = 'idle' | 'connecting' | 'realtime' | 'fallback_polling';

export function useRequestPolling(params: UseRequestPollingParams) {
  const {
    auth,
    adminViewMode,
    customerRequestIdParsed,
    driverJobRequestIdParsed,
    setError,
    onRealtimeEvent,
  } = params;

  const [requestDetails, setRequestDetails] = useState<WasteRequestDetails | null>(null);
  const [syncState, setSyncState] = useState<RealtimeSyncState>('idle');
  const lastEventIdRef = useRef<string | null>(null);

  const pollingRequestId = useMemo(() => {
    if (!auth) {
      return null;
    }

    if (auth.user.role === 'customer') {
      return customerRequestIdParsed;
    }

    if (auth.user.role === 'driver') {
      return driverJobRequestIdParsed;
    }

    if (adminViewMode === 'customer') {
      return customerRequestIdParsed;
    }

    return driverJobRequestIdParsed;
  }, [auth, adminViewMode, customerRequestIdParsed, driverJobRequestIdParsed]);

  const fetchRequestSnapshot = useCallback(
    async (requestId: number, token: string): Promise<WasteRequestDetails> => {
      const [details, latest, compliance] = await Promise.all([
        apiClient.getWasteRequest(requestId, token),
        apiClient.getLatestLocation(requestId, token),
        apiClient.getWasteRequestCompliance(requestId, token).catch(() => null),
      ]);

      return {
        ...details,
        latest_location: latest?.latest_location || details.latest_location,
        compliance: compliance
          ? {
              documents: compliance.documents,
              summary: compliance.summary,
            }
          : details.compliance,
      };
    },
    [],
  );

  useEffect(() => {
    if (!auth || !pollingRequestId) {
      lastEventIdRef.current = null;
      setSyncState('idle');
      return;
    }

    lastEventIdRef.current = null;
    let cancelled = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let fallbackInterval: ReturnType<typeof setInterval> | null = null;
    const abortController = new AbortController();

    const stopFallbackPolling = () => {
      if (!fallbackInterval) {
        return;
      }
      clearInterval(fallbackInterval);
      fallbackInterval = null;
    };

    const pollSnapshotOnce = async () => {
      if (cancelled) {
        return;
      }
      try {
        const snapshot = await fetchRequestSnapshot(pollingRequestId, auth.access_token);
        if (!cancelled) {
          setRequestDetails(snapshot);
        }
      } catch (err) {
        if (!cancelled) {
          setError(normalizeError(err));
        }
      }
    };

    const startFallbackPolling = () => {
      if (cancelled) {
        return;
      }
      setSyncState('fallback_polling');
      if (fallbackInterval) {
        return;
      }
      void pollSnapshotOnce();
      fallbackInterval = setInterval(() => {
        void pollSnapshotOnce();
      }, apiClient.realtimeFallbackPollIntervalMs);
    };

    const connect = async () => {
      if (cancelled) {
        return;
      }

      setSyncState('connecting');
      try {
        await apiClient.streamWasteRequestEvents(pollingRequestId, auth.access_token, {
          signal: abortController.signal,
          lastEventId: lastEventIdRef.current,
          onOpen: () => {
            if (!cancelled) {
              stopFallbackPolling();
              setError(null);
              setSyncState('realtime');
            }
          },
          onEvent: (event) => {
            if (cancelled) {
              return;
            }
            if (event.event_id !== undefined && event.event_id !== null) {
              lastEventIdRef.current = String(event.event_id);
            }
            if (event.payload) {
              setRequestDetails(event.payload);
            }
            onRealtimeEvent?.(event);
          },
        });

        if (!cancelled && !abortController.signal.aborted) {
          startFallbackPolling();
          reconnectTimer = setTimeout(connect, apiClient.realtimeReconnectDelayMs);
        }
      } catch (err) {
        if (cancelled || abortController.signal.aborted) {
          return;
        }
        setError(normalizeError(err));
        startFallbackPolling();
        reconnectTimer = setTimeout(connect, apiClient.realtimeReconnectDelayMs);
      }
    };

    const hydrateAndConnect = async () => {
      try {
        const snapshot = await fetchRequestSnapshot(pollingRequestId, auth.access_token);
        if (!cancelled) {
          setRequestDetails(snapshot);
        }
      } catch (err) {
        if (!cancelled) {
          setError(normalizeError(err));
        }
      }

      if (!cancelled) {
        connect();
      }
    };

    hydrateAndConnect();

    return () => {
      cancelled = true;
      abortController.abort();
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
      }
      stopFallbackPolling();
    };
  }, [auth, fetchRequestSnapshot, onRealtimeEvent, pollingRequestId, setError]);

  const isPolling = syncState === 'connecting' || syncState === 'fallback_polling';
  const isRealtimeConnected = syncState === 'realtime';
  const isFallbackPolling = syncState === 'fallback_polling';

  return {
    requestDetails,
    setRequestDetails,
    isPolling,
    isRealtimeConnected,
    isFallbackPolling,
    syncState,
    fetchRequestSnapshot,
  };
}
