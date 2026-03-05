import { useCallback } from 'react';
import type {
  AuthResponse,
  CreateWasteRequestResponse,
  WasteRequestDetails,
} from '../../../api/client';
import { apiClient } from '../../../api/client';
import type {
  CustomerScreen,
  DriverJobState,
  DriverOfferState,
  RequestFormState,
} from '../types';
import { normalizeError } from './utils';

type UseCustomerRequestActionsParams = {
  auth: AuthResponse | null;
  form: RequestFormState;
  customerRequestIdParsed: number | null;
  fetchRequestSnapshot: (requestId: number, token: string) => Promise<WasteRequestDetails>;
  setRequestDetails: React.Dispatch<React.SetStateAction<WasteRequestDetails | null>>;
  setCreated: React.Dispatch<React.SetStateAction<CreateWasteRequestResponse | null>>;
  setCustomerRequestId: React.Dispatch<React.SetStateAction<string>>;
  setDriverOffer: React.Dispatch<React.SetStateAction<DriverOfferState>>;
  setDriverJob: React.Dispatch<React.SetStateAction<DriverJobState>>;
  setCustomerScreen: React.Dispatch<React.SetStateAction<CustomerScreen>>;
  setError: React.Dispatch<React.SetStateAction<string | null>>;
  setInfo: React.Dispatch<React.SetStateAction<string | null>>;
  setIsLoading: React.Dispatch<React.SetStateAction<boolean>>;
};

export function useCustomerRequestActions(params: UseCustomerRequestActionsParams) {
  const {
    auth,
    form,
    customerRequestIdParsed,
    fetchRequestSnapshot,
    setRequestDetails,
    setCreated,
    setCustomerRequestId,
    setDriverOffer,
    setDriverJob,
    setCustomerScreen,
    setError,
    setInfo,
    setIsLoading,
  } = params;

  const onCreateRequest = useCallback(async () => {
    if (!auth) {
      return;
    }

    const schedule = new Date(form.scheduledPickupAtLocal);
    if (Number.isNaN(schedule.getTime())) {
      setError('Scheduled pickup date must be a valid datetime format (YYYY-MM-DDTHH:mm).');
      return;
    }

    const wasteAmount = Number(form.wasteAmount);
    const radiusMiles = Number(form.matchRadiusMiles);

    if (!Number.isFinite(wasteAmount) || wasteAmount <= 0) {
      setError('Waste amount must be a positive number.');
      return;
    }

    if (!Number.isFinite(radiusMiles) || radiusMiles <= 0) {
      setError('Match radius must be a positive number.');
      return;
    }

    setError(null);
    setInfo(null);
    setIsLoading(true);

    try {
      const response = await apiClient.createWasteRequest(
        {
          requester_name: form.requesterName.trim(),
          requester_email: form.requesterEmail.trim().toLowerCase(),
          material_type: form.materialType.trim(),
          custom_material_type: form.customMaterialType.trim() || undefined,
          waste_amount: wasteAmount,
          waste_unit: form.wasteUnit.trim(),
          match_radius_miles: radiusMiles,
          pickup_address: form.pickupAddress.trim(),
          pickup_city: form.pickupCity.trim() || undefined,
          pickup_county: form.pickupCounty.trim() || undefined,
          pickup_postcode: form.pickupPostcode.trim(),
          scheduled_pickup_at: schedule.toISOString(),
          notes: form.notes.trim() || undefined,
        },
        auth.access_token,
      );

      const requestId = String(response.request.id);
      setCreated(response);
      setCustomerRequestId(requestId);
      setDriverOffer((prev) => ({ ...prev, requestId }));
      setDriverJob((prev) => ({ ...prev, requestId }));
      setCustomerScreen('request-status');

      const snapshot = await fetchRequestSnapshot(response.request.id, auth.access_token);
      setRequestDetails(snapshot);

      setInfo(
        `Created waste request #${response.request.id}. Dispatch offers: ${response.dispatch?.offers_created ?? 0}.`,
      );
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setIsLoading(false);
    }
  }, [
    auth,
    fetchRequestSnapshot,
    form,
    setCreated,
    setCustomerRequestId,
    setCustomerScreen,
    setDriverJob,
    setDriverOffer,
    setError,
    setInfo,
    setIsLoading,
    setRequestDetails,
  ]);

  const onRefreshNow = useCallback(async () => {
    if (!auth || !customerRequestIdParsed) {
      return;
    }

    setError(null);
    setInfo(null);
    setIsLoading(true);

    try {
      const snapshot = await fetchRequestSnapshot(customerRequestIdParsed, auth.access_token);
      setRequestDetails(snapshot);
      setInfo(`Fetched request #${customerRequestIdParsed}.`);
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setIsLoading(false);
    }
  }, [
    auth,
    customerRequestIdParsed,
    fetchRequestSnapshot,
    setError,
    setInfo,
    setIsLoading,
    setRequestDetails,
  ]);

  return {
    onCreateRequest,
    onRefreshNow,
  };
}
