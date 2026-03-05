import React from 'react';
import { Button, Pressable, StyleSheet, Text, View } from 'react-native';
import type { UpdateStatusPayload, WasteRequestDetails } from '../../api/client';
import { Field } from '../../components/Field';
import { RequestDetailsPanel } from '../../components/RequestDetailsPanel';
import type { DriverJobState } from '../../features/wasteMobile/types';

type ActiveJobScreenProps = {
  driverJob: DriverJobState;
  setDriverJob: React.Dispatch<React.SetStateAction<DriverJobState>>;
  isLoading: boolean;
  onLoadDriverJob: () => void;
  onUpdateDriverStatus: (status: UpdateStatusPayload['status']) => void;
  onPushLocation: () => void;
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
    statuses,
    relevantRequestDetails,
  } = props;

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
});
