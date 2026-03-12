import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { apiClient } from '../api/client';

export function AdminLaunchBillingCard() {
  if (apiClient.paymentsEnabled) {
    return null;
  }

  return (
    <View style={styles.card}>
      <Text style={styles.title}>Launch Billing Mode</Text>
      <Text style={styles.status}>Offline invoicing is active for launch.</Text>
      <Text style={styles.step}>1. Confirm booking and driver assignment in the app.</Text>
      <Text style={styles.step}>2. Invoice the customer outside the app.</Text>
      <Text style={styles.step}>3. Pay carriers or drivers outside the app.</Text>
      <Text style={styles.step}>4. Treat any refund or dispute handling as an external finance workflow.</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#9fc59a',
    backgroundColor: '#eef6ec',
    padding: 12,
    gap: 6,
  },
  title: {
    fontSize: 16,
    fontWeight: '700',
    color: '#1d4d1a',
  },
  status: {
    fontWeight: '600',
    color: '#2d5e28',
  },
  step: {
    color: '#2d5e28',
  },
});
