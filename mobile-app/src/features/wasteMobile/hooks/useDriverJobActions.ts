import { useCallback } from 'react';
import type {
  AuthResponse,
  CreateComplianceDocumentPayload,
  UpdateStatusPayload,
  WasteRequestDetails,
} from '../../../api/client';
import { apiClient, ApiError } from '../../../api/client';
import {
  defaultComplianceUploadState,
  type ComplianceUploadState,
  type DriverJobState,
  type DriverOfferState,
  type DriverScreen,
} from '../types';
import { normalizeError, parsePositiveInt } from './utils';

type UseDriverJobActionsParams = {
  auth: AuthResponse | null;
  driverOffer: DriverOfferState;
  driverJob: DriverJobState;
  fetchRequestSnapshot: (requestId: number, token: string) => Promise<WasteRequestDetails>;
  setRequestDetails: React.Dispatch<React.SetStateAction<WasteRequestDetails | null>>;
  setCustomerRequestId: React.Dispatch<React.SetStateAction<string>>;
  complianceUpload: ComplianceUploadState;
  setComplianceUpload: React.Dispatch<React.SetStateAction<ComplianceUploadState>>;
  setDriverJob: React.Dispatch<React.SetStateAction<DriverJobState>>;
  setDriverScreen: React.Dispatch<React.SetStateAction<DriverScreen>>;
  onRefreshDriverCompliance?: () => Promise<void> | void;
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
    complianceUpload,
    setComplianceUpload,
    setDriverJob,
    setDriverScreen,
    onRefreshDriverCompliance,
    setError,
    setInfo,
    setIsLoading,
  } = params;

  const uploadViaSignedUrl = useCallback(
    async (requestId: number, uri: string, fileName: string, mimeType: string) => {
      const signed = await apiClient.createSignedComplianceUpload(
        requestId,
        {
          document_type: complianceUpload.documentType,
          file_name: fileName,
          mime_type: mimeType,
        },
        auth!.access_token,
      );

      const localResponse = await fetch(uri);
      if (!localResponse.ok) {
        throw new Error(`Failed to read local file (${localResponse.status}).`);
      }
      const fileBlob = await localResponse.blob();
      const uploadResponse = await fetch(signed.upload_url, {
        method: signed.method || 'PUT',
        headers: signed.headers,
        body: fileBlob,
      });

      if (!uploadResponse.ok) {
        throw new Error(`Signed upload failed (${uploadResponse.status}).`);
      }

      return signed.upload.file_url;
    },
    [auth, complianceUpload.documentType],
  );

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

  const onUploadComplianceDocument = useCallback(async () => {
    if (!auth) {
      return;
    }

    const requestId = parsePositiveInt(driverJob.requestId);
    let fileUrl = complianceUpload.fileUrl.trim();
    const documentReference = complianceUpload.documentReference.trim();

    if (!requestId) {
      setError('Assigned request ID must be a positive integer.');
      return;
    }

    if (!fileUrl) {
      setError('Evidence file is required.');
      return;
    }

    setError(null);
    setInfo(null);
    setIsLoading(true);

    try {
      if (!/^https?:\/\//i.test(fileUrl)) {
        const fileName =
          complianceUpload.fileName ||
          `${complianceUpload.documentType}.${complianceUpload.mimeType.includes('pdf') ? 'pdf' : 'jpg'}`;
        const mimeType = complianceUpload.mimeType || 'application/octet-stream';

        try {
          fileUrl = await uploadViaSignedUrl(requestId, fileUrl, fileName, mimeType);
        } catch (err) {
          const signedUploadUnavailable =
            (err instanceof ApiError && err.status === 409) ||
            (err instanceof Error && /Signed uploads require S3 storage backend/.test(err.message));
          if (!signedUploadUnavailable) {
            throw err;
          }

          const upload = await apiClient.uploadComplianceFile(
            requestId,
            {
              document_type: complianceUpload.documentType,
              uri: fileUrl,
              file_name: fileName,
              mime_type: mimeType,
            },
            auth.access_token,
          );
          fileUrl = upload.upload.file_url;
        }
      }

      const payload: CreateComplianceDocumentPayload = {
        document_type: complianceUpload.documentType,
        file_url: fileUrl,
        document_reference: documentReference || undefined,
      };
      const response = await apiClient.createComplianceDocument(requestId, payload, auth.access_token);
      const snapshot = await fetchRequestSnapshot(requestId, auth.access_token);
      setRequestDetails(snapshot);
      await onRefreshDriverCompliance?.();
      setCustomerRequestId(String(requestId));
      setComplianceUpload((prev) => ({
        ...prev,
        fileUrl: defaultComplianceUploadState.fileUrl,
        fileName: defaultComplianceUploadState.fileName,
        mimeType: defaultComplianceUploadState.mimeType,
        documentReference: defaultComplianceUploadState.documentReference,
      }));
      setInfo(
        `Uploaded ${response.document.document_type.replace(/_/g, ' ')} for request #${requestId}.`,
      );
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setIsLoading(false);
    }
  }, [
    auth,
    complianceUpload.documentReference,
    complianceUpload.documentType,
    complianceUpload.fileUrl,
    complianceUpload.fileName,
    complianceUpload.mimeType,
    driverJob.requestId,
    fetchRequestSnapshot,
    setComplianceUpload,
    setCustomerRequestId,
    setError,
    setInfo,
    setIsLoading,
    setRequestDetails,
    onRefreshDriverCompliance,
    uploadViaSignedUrl,
  ]);

  return {
    onAcceptDispatchOffer,
    onLoadDriverJob,
    onUpdateDriverStatus,
    onPushLocation,
    onUploadComplianceDocument,
  };
}
