import { Alert } from 'react-native';
import { useCallback, useMemo, useState } from 'react';
import type { CreateWasteRequestResponse, WasteRequestRealtimeEvent } from '../../../api/client';
import {
  defaultDriverJobState,
  defaultDriverOfferState,
  defaultFormState,
  type AdminViewMode,
  type CustomerScreen,
  type DriverJobState,
  type DriverOfferState,
  type DriverScreen,
  type RequestFormState,
} from '../types';
import { useAuthSession } from './useAuthSession';
import { useCustomerRequestActions } from './useCustomerRequestActions';
import { useDriverJobActions } from './useDriverJobActions';
import { useOsPushNotifications } from './useOsPushNotifications';
import { useRequestPolling } from './useRequestPolling';
import { parsePositiveInt } from './utils';

export function useWasteMobileController() {
  const [form, setForm] = useState<RequestFormState>(defaultFormState);
  const [customerRequestId, setCustomerRequestId] = useState('');
  const [driverOffer, setDriverOffer] = useState<DriverOfferState>(defaultDriverOfferState);
  const [driverJob, setDriverJob] = useState<DriverJobState>(defaultDriverJobState);

  const [created, setCreated] = useState<CreateWasteRequestResponse | null>(null);
  const [customerScreen, setCustomerScreen] = useState<CustomerScreen>('new-request');
  const [driverScreen, setDriverScreen] = useState<DriverScreen>('offer-inbox');
  const [adminViewMode, setAdminViewMode] = useState<AdminViewMode>('customer');

  const [isLoading, setIsLoading] = useState(false);
  const [info, setInfo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const {
    authScreen,
    setAuthScreen,
    login,
    setLogin,
    signup,
    setSignup,
    verifyRequest,
    setVerifyRequest,
    verifyConfirm,
    setVerifyConfirm,
    passwordResetRequest,
    setPasswordResetRequest,
    passwordResetConfirm,
    setPasswordResetConfirm,
    auth,
    isBootstrappingSession,
    onLogin,
    onSignup,
    onRequestEmailVerification,
    onConfirmEmailVerification,
    onRequestPasswordReset,
    onConfirmPasswordReset,
    onLogout: onSessionLogout,
  } = useAuthSession({
    setForm,
    setInfo,
    setError,
    setIsLoading,
  });

  const { onBeforeLogout } = useOsPushNotifications({
    auth,
    setError,
    setInfo,
  });

  const customerRequestIdParsed = parsePositiveInt(customerRequestId);
  const driverJobRequestIdParsed = parsePositiveInt(driverJob.requestId);

  const hasTrackedCustomerRequest = customerRequestIdParsed !== null;

  const onRealtimeEvent = useCallback((event: WasteRequestRealtimeEvent) => {
    if (event.event === 'snapshot' || event.event === 'location_updated') {
      return;
    }

    const eventLabelByType: Record<string, string> = {
      snapshot: 'Snapshot synced',
      request_created: 'Request created',
      dispatch_offer_accepted: 'Offer accepted',
      status_updated: 'Status updated',
      location_updated: 'Location updated',
      payment_succeeded: 'Payment succeeded',
      refund_processed: 'Refund processed',
      payout_processed: 'Payout processed',
      admin_dispatch_override: 'Dispatch override applied',
      admin_dispatch_incident_ack: 'Incident acknowledged',
      admin_dispatch_incident_resolve: 'Incident resolved',
      admin_dispatch_incident_owner_reassign: 'Incident owner updated',
    };
    const eventLabel =
      eventLabelByType[event.event] || event.event.replace(/_/g, ' ').trim() || 'Event update';
    const requestStatus = event.payload?.request?.status || 'unknown';
    const message = `${eventLabel} for request #${event.request_id} (${requestStatus}).`;

    setInfo(message);
    Alert.alert('Live update', message);
  }, []);

  const {
    requestDetails,
    setRequestDetails,
    isPolling,
    isRealtimeConnected,
    isFallbackPolling,
    syncState,
    fetchRequestSnapshot,
  } = useRequestPolling({
    auth,
    adminViewMode,
    customerRequestIdParsed,
    driverJobRequestIdParsed,
    setError,
    onRealtimeEvent,
  });

  const customerRelevantRequestDetails = useMemo(() => {
    if (!requestDetails || !customerRequestIdParsed) {
      return null;
    }
    return requestDetails.request.id === customerRequestIdParsed ? requestDetails : null;
  }, [requestDetails, customerRequestIdParsed]);

  const driverRelevantRequestDetails = useMemo(() => {
    if (!requestDetails || !driverJobRequestIdParsed) {
      return null;
    }
    return requestDetails.request.id === driverJobRequestIdParsed ? requestDetails : null;
  }, [requestDetails, driverJobRequestIdParsed]);

  const { onCreateRequest, onRefreshNow } = useCustomerRequestActions({
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
  });

  const {
    onAcceptDispatchOffer,
    onLoadDriverJob,
    onUpdateDriverStatus,
    onPushLocation,
  } = useDriverJobActions({
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
  });

  const onLogout = useCallback(async () => {
    await onBeforeLogout();
    await onSessionLogout();

    setForm(defaultFormState());
    setCustomerRequestId('');
    setDriverOffer(defaultDriverOfferState);
    setDriverJob(defaultDriverJobState);
    setCreated(null);
    setRequestDetails(null);
    setCustomerScreen('new-request');
    setDriverScreen('offer-inbox');
    setAdminViewMode('customer');
    setInfo('Signed out.');
  }, [onBeforeLogout, onSessionLogout, setRequestDetails]);

  const onSelectCustomerScreen = useCallback((id: string) => {
    setCustomerScreen(id as CustomerScreen);
  }, []);

  const onSelectDriverScreen = useCallback((id: string) => {
    setDriverScreen(id as DriverScreen);
  }, []);

  const currentRole = auth?.user.role || null;

  return {
    authScreen,
    setAuthScreen,
    login,
    setLogin,
    signup,
    setSignup,
    verifyRequest,
    setVerifyRequest,
    verifyConfirm,
    setVerifyConfirm,
    passwordResetRequest,
    setPasswordResetRequest,
    passwordResetConfirm,
    setPasswordResetConfirm,
    auth,
    form,
    setForm,
    customerRequestId,
    setCustomerRequestId,
    driverOffer,
    setDriverOffer,
    driverJob,
    setDriverJob,
    created,
    customerScreen,
    onSelectCustomerScreen,
    driverScreen,
    onSelectDriverScreen,
    adminViewMode,
    setAdminViewMode,
    isLoading,
    isPolling,
    isRealtimeConnected,
    isFallbackPolling,
    syncState,
    isBootstrappingSession,
    info,
    error,
    hasTrackedCustomerRequest,
    customerRelevantRequestDetails,
    driverRelevantRequestDetails,
    currentRole,
    onLogin,
    onSignup,
    onRequestEmailVerification,
    onConfirmEmailVerification,
    onRequestPasswordReset,
    onConfirmPasswordReset,
    onLogout,
    onCreateRequest,
    onRefreshNow,
    onAcceptDispatchOffer,
    onLoadDriverJob,
    onUpdateDriverStatus,
    onPushLocation,
  };
}
