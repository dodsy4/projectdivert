import { useCallback } from 'react';
import type {
  AuthResponse,
  UpdateStatusPayload,
  WasteRequestDetails,
} from '../../../api/client';
import { apiClient } from '../../../api/client';
import type { DriverJobState, DriverOfferState, DriverScreen } from '../types';
import { normalizeError, parsePositiveInt } from './utils';

type UseDriverJobActionsParams = {
  auth: AuthResponse | null;
  driverOffer: DriverOfferState;
  driverJob: DriverJobState;
  fetchRequestSnapshot: (requestId: number, token: string) => Promise<WasteRequestDetails>;
  setRequestDetails: React.Dispatch<React.SetStateAction<WasteRequestDetails | null>>;
  setCustomerRequestId: React.Dispatch<React.SetStateAction<string>>;
  setDriverJob: React.Dispatch<React.SetStateAction<DriverJobState>>;
  setDriverScreen: React.Dispatch<React.SetStateAction<DriverScreen>>;
  setError: React.Dispatch<React.SetStateAction<string | null>>;
  setInfo: React.Dispatch<React.SetStateAction<string | null>>;
  setIsLoading: React.Dispatch<React.SetStateAction<boolean>>;
};

export function useDriverJobActions(params: UseDriverJobActionsParams) {
  const {
    auth,
    driverOffer,
    driverJob,
    fetchRequestSnapshot,
    setRequestDetails,
    setCustomerRequestId,
    setDriverJob,
    setDriverScreen,
    setError,
    setInfo,
    setIsLoading,
  } = params;

  const onAcceptDispatchOffer = useCallback(async () => {
    if (!auth) {
      return;
    }

    const requestId = parsePositiveInt(driverOffer.requestId);
    const offerToken = driverOffer.offerToken.trim();

    if (!requestId) {
      setError('Driver request ID must be a positive integer.');
      return;
    }

    if (!offerToken) {
      setError('Offer token is required.');
      return;
    }

    setError(null);
    setInfo(null);
    setIsLoading(true);

    try {
      const accepted = await apiClient.acceptDispatchOffer(
        requestId,
        { offer_token: offerToken },
        auth.access_token,
      );

      setDriverJob((prev) => ({ ...prev, requestId: String(requestId) }));
      setCustomerRequestId(String(requestId));
      setDriverScreen('active-job');

      const snapshot = await fetchRequestSnapshot(requestId, auth.access_token);
      setRequestDetails({
        ...snapshot,
        dispatch: accepted.dispatch,
      });

      setInfo(
        `Accepted offer for request #${requestId}. Assigned driver user ID: ${accepted.request.assigned_driver_user_id ?? 'n/a'}.`,
      );
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setIsLoading(false);
    }
  }, [
    auth,
    driverOffer.offerToken,
    driverOffer.requestId,
    fetchRequestSnapshot,
    setCustomerRequestId,
    setDriverJob,
    setDriverScreen,
    setError,
    setInfo,
    setIsLoading,
    setRequestDetails,
  ]);

  const onLoadDriverJob = useCallback(async () => {
    if (!auth) {
      return;
    }

    const requestId = parsePositiveInt(driverJob.requestId);
    if (!requestId) {
      setError('Assigned request ID must be a positive integer.');
      return;
    }

    setError(null);
    setInfo(null);
    setIsLoading(true);

    try {
      const snapshot = await fetchRequestSnapshot(requestId, auth.access_token);
      setRequestDetails(snapshot);
      setCustomerRequestId(String(requestId));
      setInfo(`Loaded active job for request #${requestId}.`);
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setIsLoading(false);
    }
  }, [
    auth,
    driverJob.requestId,
    fetchRequestSnapshot,
    setCustomerRequestId,
    setError,
    setInfo,
    setIsLoading,
    setRequestDetails,
  ]);

  const onUpdateDriverStatus = useCallback(
    async (status: UpdateStatusPayload['status']) => {
      if (!auth) {
        return;
      }

      const requestId = parsePositiveInt(driverJob.requestId);
      if (!requestId) {
        setError('Assigned request ID must be a positive integer.');
        return;
      }

      setError(null);
      setInfo(null);
      setIsLoading(true);

      try {
        await apiClient.updateWasteRequestStatus(requestId, { status }, auth.access_token);
        const snapshot = await fetchRequestSnapshot(requestId, auth.access_token);
        setRequestDetails(snapshot);
        setCustomerRequestId(String(requestId));
        setInfo(`Updated request #${requestId} to '${status}'.`);
      } catch (err) {
        setError(normalizeError(err));
      } finally {
        setIsLoading(false);
      }
    },
    [
      auth,
      driverJob.requestId,
      fetchRequestSnapshot,
      setCustomerRequestId,
      setError,
      setInfo,
      setIsLoading,
      setRequestDetails,
    ],
  );

  const onPushLocation = useCallback(async () => {
    if (!auth) {
      return;
    }

    const requestId = parsePositiveInt(driverJob.requestId);
    const latitude = Number(driverJob.latitude);
    const longitude = Number(driverJob.longitude);

    if (!requestId) {
      setError('Assigned request ID must be a positive integer.');
      return;
    }

    if (Number.isNaN(latitude) || Number.isNaN(longitude)) {
      setError('Latitude and longitude must be valid numbers.');
      return;
    }

    setError(null);
    setInfo(null);
    setIsLoading(true);

    try {
      await apiClient.pushVehicleLocation(
        requestId,
        {
          latitude,
          longitude,
          vehicle_id: driverJob.vehicleId.trim() || undefined,
          source: 'mobile',
        },
        auth.access_token,
      );

      const snapshot = await fetchRequestSnapshot(requestId, auth.access_token);
      setRequestDetails(snapshot);
      setCustomerRequestId(String(requestId));
      setInfo(`Sent location update for request #${requestId}.`);
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setIsLoading(false);
    }
  }, [
    auth,
    driverJob.latitude,
    driverJob.longitude,
    driverJob.requestId,
    driverJob.vehicleId,
    fetchRequestSnapshot,
    setCustomerRequestId,
    setError,
    setInfo,
    setIsLoading,
    setRequestDetails,
  ]);

  return {
    onAcceptDispatchOffer,
    onLoadDriverJob,
    onUpdateDriverStatus,
    onPushLocation,
  };
}
