import { Alert } from 'react-native';
import { useCallback, useEffect, useMemo, useState } from 'react';
import type {
  AdminComplianceReviewQueueResponse,
  CreateWasteRequestResponse,
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

  const [created, setCreated] = useState<CreateWasteRequestResponse | null>(null);
  const [customerScreen, setCustomerScreen] = useState<CustomerScreen>('new-request');
  const [driverScreen, setDriverScreen] = useState<DriverScreen>('offer-inbox');
  const [adminViewMode, setAdminViewMode] = useState<AdminViewMode>('customer');

  const [isLoading, setIsLoading] = useState(false);
  const [isComplianceQueueLoading, setIsComplianceQueueLoading] = useState(false);
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
      onLoadComplianceReviewQueue,
      setError,
      setInfo,
      setRequestDetails,
    ],
  );

  useEffect(() => {
    if (auth?.user.role !== 'admin') {
      setAdminComplianceReviewQueue(null);
      return;
    }

    void onLoadComplianceReviewQueue();
  }, [auth?.user.role, onLoadComplianceReviewQueue]);

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
    info,
    error,
    hasTrackedCustomerRequest,
    customerRelevantRequestDetails,
    driverRelevantRequestDetails,
    adminComplianceReviewQueue,
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
    onReviewComplianceDocument,
  };
}
