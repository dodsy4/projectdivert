import { Alert } from 'react-native';
import { useCallback, useEffect, useMemo, useState } from 'react';
import type {
  AdminDriversResponse,
  AdminComplianceReviewQueueResponse,
  CreateWasteRequestResponse,
  DriverOwnComplianceResponse,
  WasteRequestRealtimeEvent,
} from '../../../api/client';
import { apiClient } from '../../../api/client';
import {
  defaultComplianceUploadState,
  defaultDriverJobState,
  defaultDriverOfferState,
  defaultFormState,
  type AdminViewMode,
  type ComplianceUploadState,
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
  const [complianceUpload, setComplianceUpload] =
    useState<ComplianceUploadState>(defaultComplianceUploadState);
  const [adminComplianceReviewQueue, setAdminComplianceReviewQueue] =
    useState<AdminComplianceReviewQueueResponse | null>(null);
  const [adminDrivers, setAdminDrivers] = useState<AdminDriversResponse | null>(null);
  const [driverOwnCompliance, setDriverOwnCompliance] = useState<DriverOwnComplianceResponse | null>(null);

  const [created, setCreated] = useState<CreateWasteRequestResponse | null>(null);
  const [customerScreen, setCustomerScreen] = useState<CustomerScreen>('new-request');
  const [driverScreen, setDriverScreen] = useState<DriverScreen>('offer-inbox');
  const [adminViewMode, setAdminViewMode] = useState<AdminViewMode>('customer');

  const [isLoading, setIsLoading] = useState(false);
  const [isComplianceQueueLoading, setIsComplianceQueueLoading] = useState(false);
  const [isAdminDriversLoading, setIsAdminDriversLoading] = useState(false);
  const [isDriverComplianceLoading, setIsDriverComplianceLoading] = useState(false);
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
      compliance_document_created: 'Compliance document uploaded',
      compliance_document_reviewed: 'Compliance document reviewed',
      admin_billing_updated: 'Billing workflow updated',
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

  const onLoadComplianceReviewQueue = useCallback(async () => {
    if (!auth || auth.user.role !== 'admin') {
      return;
    }

    setError(null);
    setIsComplianceQueueLoading(true);

    try {
      const queue = await apiClient.getAdminComplianceReviewQueue(auth.access_token, {
        status: 'submitted',
        limit: 20,
      });
      setAdminComplianceReviewQueue(queue);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load compliance review queue.');
    } finally {
      setIsComplianceQueueLoading(false);
    }
  }, [auth, setError]);

  const onLoadAdminDrivers = useCallback(async () => {
    if (!auth || auth.user.role !== 'admin') {
      return;
    }

    setError(null);
    setIsAdminDriversLoading(true);

    try {
      const drivers = await apiClient.getAdminDrivers(auth.access_token, {
        active: true,
        limit: 20,
      });
      setAdminDrivers(drivers);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load driver eligibility.');
    } finally {
      setIsAdminDriversLoading(false);
    }
  }, [auth, setError]);

  const onLoadDriverOwnCompliance = useCallback(async () => {
    if (!auth || auth.user.role !== 'driver') {
      return;
    }

    setError(null);
    setIsDriverComplianceLoading(true);

    try {
      const profile = await apiClient.getDriverOwnCompliance(auth.access_token);
      setDriverOwnCompliance(profile);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load your dispatch eligibility.');
    } finally {
      setIsDriverComplianceLoading(false);
    }
  }, [auth, setError]);

  const {
    onAcceptDispatchOffer,
    onLoadDriverJob,
    onUpdateDriverStatus,
    onPushLocation,
    onUploadComplianceDocument,
  } = useDriverJobActions({
    auth,
    driverOffer,
    driverJob,
    fetchRequestSnapshot,
    setRequestDetails,
    setCustomerRequestId,
    complianceUpload,
    setComplianceUpload,
    setDriverJob,
    setDriverScreen,
    onRefreshDriverCompliance: onLoadDriverOwnCompliance,
    setError,
    setInfo,
    setIsLoading,
  });

  const onReviewComplianceDocument = useCallback(
    async (requestId: number, documentId: number, status: 'verified' | 'rejected') => {
      if (!auth || auth.user.role !== 'admin') {
        return;
      }

      setError(null);
      setInfo(null);
      setIsComplianceQueueLoading(true);

      try {
        await apiClient.reviewComplianceDocument(
          requestId,
          documentId,
          { status },
          auth.access_token,
        );
        await onLoadComplianceReviewQueue();
        await onLoadAdminDrivers();

        const activeRequestId =
          customerRequestIdParsed === requestId || driverJobRequestIdParsed === requestId
            ? requestId
            : null;
        if (activeRequestId) {
          const snapshot = await fetchRequestSnapshot(activeRequestId, auth.access_token);
          setRequestDetails(snapshot);
        }

        setInfo(`Marked compliance document #${documentId} as ${status}.`);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unable to review compliance document.');
      } finally {
        setIsComplianceQueueLoading(false);
      }
    },
    [
      auth,
      customerRequestIdParsed,
      driverJobRequestIdParsed,
      fetchRequestSnapshot,
      onLoadAdminDrivers,
      onLoadComplianceReviewQueue,
      setError,
      setInfo,
      setRequestDetails,
    ],
  );

  useEffect(() => {
    if (auth?.user.role !== 'admin') {
      setAdminComplianceReviewQueue(null);
      setAdminDrivers(null);
      return;
    }

    void onLoadComplianceReviewQueue();
    void onLoadAdminDrivers();
  }, [auth?.user.role, onLoadAdminDrivers, onLoadComplianceReviewQueue]);

  useEffect(() => {
    if (auth?.user.role !== 'driver') {
      setDriverOwnCompliance(null);
      return;
    }

    void onLoadDriverOwnCompliance();
  }, [auth?.user.role, onLoadDriverOwnCompliance]);

  const onUpdateBillingWorkflow = useCallback(
    async (requestId: number, payload: { state: string; reference?: string; notes?: string }) => {
      if (!auth || auth.user.role !== 'admin') {
        return;
      }

      setError(null);
      setInfo(null);
      setIsLoading(true);

      try {
        await apiClient.updateBillingWorkflow(requestId, payload, auth.access_token);
        const snapshot = await fetchRequestSnapshot(requestId, auth.access_token);
        setRequestDetails(snapshot);
        setInfo(`Updated offline billing workflow for request #${requestId}.`);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unable to update billing workflow.');
      } finally {
        setIsLoading(false);
      }
    },
    [auth, fetchRequestSnapshot, setError, setInfo, setIsLoading, setRequestDetails],
  );

  const onLogout = useCallback(async () => {
    await onBeforeLogout();
    await onSessionLogout();

    setForm(defaultFormState());
    setCustomerRequestId('');
    setDriverOffer(defaultDriverOfferState);
    setDriverJob(defaultDriverJobState);
    setComplianceUpload(defaultComplianceUploadState);
    setCreated(null);
    setRequestDetails(null);
    setAdminComplianceReviewQueue(null);
    setAdminDrivers(null);
    setDriverOwnCompliance(null);
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
    complianceUpload,
    setComplianceUpload,
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
    isComplianceQueueLoading,
    isAdminDriversLoading,
    isDriverComplianceLoading,
    info,
    error,
    hasTrackedCustomerRequest,
    customerRelevantRequestDetails,
    driverRelevantRequestDetails,
    adminComplianceReviewQueue,
    adminDrivers,
    driverOwnCompliance,
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
    onUploadComplianceDocument,
    onLoadComplianceReviewQueue,
    onLoadAdminDrivers,
    onLoadDriverOwnCompliance,
    onReviewComplianceDocument,
    onUpdateBillingWorkflow,
  };
}
