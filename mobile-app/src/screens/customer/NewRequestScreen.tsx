import React from 'react';
import { Button, StyleSheet, Text, View } from 'react-native';
import { apiClient } from '../../api/client';
import { Field } from '../../components/Field';
import type { RequestFormState } from '../../features/wasteMobile/types';

type NewRequestScreenProps = {
  form: RequestFormState;
  setForm: React.Dispatch<React.SetStateAction<RequestFormState>>;
  isLoading: boolean;
  onCreateRequest: () => void;
};

export function NewRequestScreen(props: NewRequestScreenProps) {
  const { form, setForm, isLoading, onCreateRequest } = props;

  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>New Waste Request</Text>
      {!apiClient.paymentsEnabled ? (
        <View style={styles.notice}>
          <Text style={styles.noticeTitle}>Offline Billing Launch Mode</Text>
          <Text style={styles.noticeText}>
            Submit the request normally. Billing will be arranged offline after booking confirmation.
          </Text>
        </View>
      ) : null}
      <Field
        label="Requester name"
        value={form.requesterName}
        onChangeText={(value) => setForm((prev) => ({ ...prev, requesterName: value }))}
      />
      <Field
        label="Requester email"
        value={form.requesterEmail}
        onChangeText={(value) => setForm((prev) => ({ ...prev, requesterEmail: value }))}
        autoCapitalize="none"
        keyboardType="email-address"
      />
      <Field
        label="Material type"
        value={form.materialType}
        onChangeText={(value) => setForm((prev) => ({ ...prev, materialType: value }))}
      />
      <Field
        label="Custom material (if Material type is Other)"
        value={form.customMaterialType}
        onChangeText={(value) => setForm((prev) => ({ ...prev, customMaterialType: value }))}
      />
      <Field
        label="Waste amount"
        value={form.wasteAmount}
        onChangeText={(value) => setForm((prev) => ({ ...prev, wasteAmount: value }))}
        keyboardType="decimal-pad"
      />
      <Field
        label="Waste unit"
        value={form.wasteUnit}
        onChangeText={(value) => setForm((prev) => ({ ...prev, wasteUnit: value }))}
      />
      <Field
        label="Match radius (miles)"
        value={form.matchRadiusMiles}
        onChangeText={(value) => setForm((prev) => ({ ...prev, matchRadiusMiles: value }))}
        keyboardType="decimal-pad"
      />
      <Field
        label="Pickup address"
        value={form.pickupAddress}
        onChangeText={(value) => setForm((prev) => ({ ...prev, pickupAddress: value }))}
      />
      <Field
        label="Pickup city"
        value={form.pickupCity}
        onChangeText={(value) => setForm((prev) => ({ ...prev, pickupCity: value }))}
      />
      <Field
        label="Pickup county"
        value={form.pickupCounty}
        onChangeText={(value) => setForm((prev) => ({ ...prev, pickupCounty: value }))}
      />
      <Field
        label="Pickup postcode"
        value={form.pickupPostcode}
        onChangeText={(value) => setForm((prev) => ({ ...prev, pickupPostcode: value }))}
        autoCapitalize="characters"
      />
      <Field
        label="Scheduled pickup (local)"
        value={form.scheduledPickupAtLocal}
        onChangeText={(value) => setForm((prev) => ({ ...prev, scheduledPickupAtLocal: value }))}
        placeholder="YYYY-MM-DDTHH:mm"
      />
      <Field
        label="Notes"
        value={form.notes}
        onChangeText={(value) => setForm((prev) => ({ ...prev, notes: value }))}
        multiline
      />
      <Button
        title={isLoading ? 'Submitting...' : 'Submit request'}
        onPress={onCreateRequest}
        disabled={isLoading}
      />
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
  notice: {
    padding: 10,
    borderRadius: 8,
    backgroundColor: '#f7f3e9',
    borderWidth: 1,
    borderColor: '#e0c98f',
    gap: 4,
  },
  noticeTitle: {
    fontSize: 14,
    fontWeight: '700',
  },
  noticeText: {
    color: '#6b5a2b',
  },
});
