import { useCallback, useEffect, useMemo, useState } from 'react';
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

const realtimeReconnectDelayMs = 2500;

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
  const [isPolling, setIsPolling] = useState(false);

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
      const [details, latest] = await Promise.all([
        apiClient.getWasteRequest(requestId, token),
        apiClient.getLatestLocation(requestId, token),
      ]);

      return {
        ...details,
        latest_location: latest?.latest_location || details.latest_location,
      };
    },
    [],
  );

  useEffect(() => {
    if (!auth || !pollingRequestId) {
      setIsPolling(false);
      return;
    }

    let cancelled = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    const abortController = new AbortController();

    const connect = async () => {
      if (cancelled) {
        return;
      }

      setIsPolling(true);
      try {
        await apiClient.streamWasteRequestEvents(pollingRequestId, auth.access_token, {
          signal: abortController.signal,
          onOpen: () => {
            if (!cancelled) {
              setError(null);
              setIsPolling(false);
            }
          },
          onEvent: (event) => {
            if (cancelled) {
              return;
            }
            if (event.payload) {
              setRequestDetails(event.payload);
            }
            onRealtimeEvent?.(event);
          },
        });

        if (!cancelled && !abortController.signal.aborted) {
          reconnectTimer = setTimeout(connect, realtimeReconnectDelayMs);
        }
      } catch (err) {
        if (cancelled || abortController.signal.aborted) {
          return;
        }
        setError(normalizeError(err));
        reconnectTimer = setTimeout(connect, realtimeReconnectDelayMs);
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
    };
  }, [auth, fetchRequestSnapshot, onRealtimeEvent, pollingRequestId, setError]);

  return {
    requestDetails,
    setRequestDetails,
    isPolling,
    fetchRequestSnapshot,
  };
}
