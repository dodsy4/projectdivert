import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';
import React, { useCallback } from 'react';
import { Alert, Button, Pressable, StyleSheet, Text, View } from 'react-native';
import type {
  ComplianceDocumentType,
  UpdateStatusPayload,
  WasteRequestDetails,
} from '../../api/client';
import { Field } from '../../components/Field';
import { RequestDetailsPanel } from '../../components/RequestDetailsPanel';
import {
  complianceUploadTypes,
  type ComplianceUploadState,
  type DriverJobState,
} from '../../features/wasteMobile/types';

type ActiveJobScreenProps = {
  driverJob: DriverJobState;
  setDriverJob: React.Dispatch<React.SetStateAction<DriverJobState>>;
  isLoading: boolean;
  onLoadDriverJob: () => void;
  onUpdateDriverStatus: (status: UpdateStatusPayload['status']) => void;
  onPushLocation: () => void;
  complianceUpload: ComplianceUploadState;
  setComplianceUpload: React.Dispatch<React.SetStateAction<ComplianceUploadState>>;
  onUploadComplianceDocument: () => void;
  statuses: UpdateStatusPayload['status'][];
  relevantRequestDetails: WasteRequestDetails | null;
};

export function ActiveJobScreen(props: ActiveJobScreenProps) {
  const {
    driverJob,
    setDriverJob,
    isLoading,
    onLoadDriverJob,
    onUpdateDriverStatus,
    onPushLocation,
    complianceUpload,
    setComplianceUpload,
    onUploadComplianceDocument,
    statuses,
    relevantRequestDetails,
  } = props;

  const completionRequiredTypes =
    relevantRequestDetails?.compliance?.summary?.completion_required_document_types || [];
  const completionMissing = completionRequiredTypes.filter(
    (documentType) => !relevantRequestDetails?.compliance?.summary?.by_type?.[documentType]?.verified,
  );
  const isPhotoEvidence = complianceUpload.documentType === 'proof_of_collection_photo';

  const applySelectedFile = useCallback(
    (
      fileUri: string,
      suggestedReference?: string | null,
      fileName?: string | null,
      mimeType?: string | null,
    ) => {
      setComplianceUpload((prev) => ({
        ...prev,
        fileUrl: fileUri,
        fileName: fileName || prev.fileName,
        mimeType: mimeType || prev.mimeType,
        documentReference: prev.documentReference || suggestedReference || prev.documentReference,
      }));
    },
    [setComplianceUpload],
  );

  const onPickDocument = useCallback(async () => {
    try {
      const result = await DocumentPicker.getDocumentAsync({
        multiple: false,
        type: ['application/pdf', 'image/*'],
      });

      if (result.canceled || !result.assets.length) {
        return;
      }

      const asset = result.assets[0];
      applySelectedFile(asset.uri, asset.name, asset.name, asset.mimeType);
    } catch (err) {
      Alert.alert('Evidence picker', err instanceof Error ? err.message : 'Unable to pick document.');
    }
  }, [applySelectedFile]);

  const onPickImageFromLibrary = useCallback(async () => {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      Alert.alert('Photo library access required', 'Allow photo access to attach collection evidence.');
      return;
    }

    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        allowsEditing: false,
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        quality: 0.8,
      });

      if (result.canceled || !result.assets.length) {
        return;
      }

      const asset = result.assets[0];
      applySelectedFile(
        asset.uri,
        asset.fileName || 'proof-photo.jpg',
        asset.fileName || 'proof-photo.jpg',
        asset.mimeType,
      );
    } catch (err) {
      Alert.alert('Evidence picker', err instanceof Error ? err.message : 'Unable to choose photo.');
    }
  }, [applySelectedFile]);

  const onTakePhoto = useCallback(async () => {
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) {
      Alert.alert('Camera access required', 'Allow camera access to capture proof-of-collection photos.');
      return;
    }

    try {
      const result = await ImagePicker.launchCameraAsync({
        allowsEditing: false,
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        quality: 0.8,
      });

      if (result.canceled || !result.assets.length) {
        return;
      }

      const asset = result.assets[0];
      applySelectedFile(
        asset.uri,
        asset.fileName || 'proof-photo.jpg',
        asset.fileName || 'proof-photo.jpg',
        asset.mimeType,
      );
    } catch (err) {
      Alert.alert('Camera', err instanceof Error ? err.message : 'Unable to capture photo.');
    }
  }, [applySelectedFile]);

  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>Active Job</Text>
      <Field
        label="Assigned request ID"
        value={driverJob.requestId}
        onChangeText={(value) => setDriverJob((prev) => ({ ...prev, requestId: value }))}
        keyboardType="number-pad"
      />
      <Button
        title={isLoading ? 'Loading...' : 'Load job'}
        onPress={onLoadDriverJob}
        disabled={isLoading}
      />

      {relevantRequestDetails ? <RequestDetailsPanel details={relevantRequestDetails} /> : null}

      <View style={styles.resultBlock}>
        <Text style={styles.blockTitle}>Status Flow</Text>
        {completionMissing.length ? (
          <Text style={styles.warningText}>
            Completion blocked until verified: {completionMissing.join(', ')}
          </Text>
        ) : null}
        <View style={styles.buttonGrid}>
          {statuses.map((status) => (
            <Pressable
              key={status}
              style={styles.smallAction}
              onPress={() => onUpdateDriverStatus(status)}
              disabled={isLoading}
            >
              <Text style={styles.smallActionText}>{status}</Text>
            </Pressable>
          ))}
        </View>
      </View>

      <View style={styles.resultBlock}>
        <Text style={styles.blockTitle}>Collection Evidence</Text>
        <View style={styles.buttonGrid}>
          {complianceUploadTypes.map((documentType) => {
            const selected = complianceUpload.documentType === documentType;
            return (
              <Pressable
                key={documentType}
                style={[styles.smallAction, selected ? styles.selectedAction : undefined]}
              onPress={() =>
                setComplianceUpload((prev) => ({
                  ...prev,
                  documentType: documentType as ComplianceDocumentType,
                  fileUrl: '',
                  fileName: '',
                  mimeType: '',
                }))
              }
              disabled={isLoading}
              >
                <Text style={styles.smallActionText}>{documentType.replace(/_/g, ' ')}</Text>
              </Pressable>
            );
          })}
        </View>
        <View style={styles.buttonGrid}>
          {isPhotoEvidence ? (
            <>
              <Pressable style={styles.smallAction} onPress={onTakePhoto} disabled={isLoading}>
                <Text style={styles.smallActionText}>take photo</Text>
              </Pressable>
              <Pressable
                style={styles.smallAction}
                onPress={onPickImageFromLibrary}
                disabled={isLoading}
              >
                <Text style={styles.smallActionText}>choose photo</Text>
              </Pressable>
            </>
          ) : (
            <Pressable style={styles.smallAction} onPress={onPickDocument} disabled={isLoading}>
              <Text style={styles.smallActionText}>choose file</Text>
            </Pressable>
          )}
          {complianceUpload.fileUrl ? (
            <Pressable
              style={styles.smallAction}
              onPress={() =>
                setComplianceUpload((prev) => ({
                  ...prev,
                  fileUrl: '',
                  fileName: '',
                  mimeType: '',
                }))
              }
              disabled={isLoading}
            >
              <Text style={styles.smallActionText}>clear file</Text>
            </Pressable>
          ) : null}
        </View>
        <Text style={styles.helperText}>
          {complianceUpload.fileUrl
            ? `Selected file: ${complianceUpload.fileName || complianceUpload.fileUrl}`
            : isPhotoEvidence
              ? 'Capture or choose the proof-of-collection photo.'
              : 'Choose the waste transfer note file from this device.'}
        </Text>
        <Field
          label="Document Reference"
          value={complianceUpload.documentReference}
          onChangeText={(value) =>
            setComplianceUpload((prev) => ({ ...prev, documentReference: value }))
          }
        />
        <Button
          title={isLoading ? 'Uploading...' : 'Upload evidence'}
          onPress={onUploadComplianceDocument}
          disabled={isLoading || !complianceUpload.fileUrl}
        />
      </View>

      <View style={styles.resultBlock}>
        <Text style={styles.blockTitle}>Location Update</Text>
        <Field
          label="Latitude"
          value={driverJob.latitude}
          onChangeText={(value) => setDriverJob((prev) => ({ ...prev, latitude: value }))}
          keyboardType="decimal-pad"
        />
        <Field
          label="Longitude"
          value={driverJob.longitude}
          onChangeText={(value) => setDriverJob((prev) => ({ ...prev, longitude: value }))}
          keyboardType="decimal-pad"
        />
        <Field
          label="Vehicle ID"
          value={driverJob.vehicleId}
          onChangeText={(value) => setDriverJob((prev) => ({ ...prev, vehicleId: value }))}
        />
        <Button
          title={isLoading ? 'Sending...' : 'Push location'}
          onPress={onPushLocation}
          disabled={isLoading}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#d8d8d8',
    backgroundColor: '#ffffff',
    padding: 12,
    gap: 8,
  },
  cardTitle: {
    fontSize: 16,
    fontWeight: '700',
  },
  resultBlock: {
    borderTopWidth: 1,
    borderColor: '#e5e5e5',
    marginTop: 8,
    paddingTop: 8,
    gap: 4,
  },
  blockTitle: {
    fontSize: 14,
    fontWeight: '700',
  },
  buttonGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  smallAction: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#14529a',
    backgroundColor: '#e6f0ff',
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  smallActionText: {
    color: '#0f3d74',
    fontWeight: '700',
    textTransform: 'capitalize',
  },
  selectedAction: {
    borderColor: '#0f5132',
    backgroundColor: '#d9fbe6',
  },
  warningText: {
    color: '#9a3412',
    fontWeight: '600',
  },
  helperText: {
    color: '#4b5563',
    fontSize: 12,
  },
});
