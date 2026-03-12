import React from 'react';
import { Button, StyleSheet, Text, View } from 'react-native';
import type { AdminDriversResponse } from '../api/client';

type AdminDriverEligibilityCardProps = {
  drivers: AdminDriversResponse | null;
  isLoading: boolean;
  onRefresh: () => void;
};

function formatReason(reason: string) {
  const [scope, code] = reason.split(':');
  if (!code) {
    return reason;
  }
  return `${scope} ${code}`.replace(/_/g, ' ');
}

export function AdminDriverEligibilityCard(props: AdminDriverEligibilityCardProps) {
  const { drivers, isLoading, onRefresh } = props;

  const items = drivers?.items || [];
  const eligibleCount = items.filter((item) => item.dispatch_eligible).length;
  const blockedCount = items.length - eligibleCount;

  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>Driver Eligibility</Text>
      <Button
        title={isLoading ? 'Refreshing...' : 'Refresh drivers'}
        onPress={onRefresh}
        disabled={isLoading}
      />

      {!drivers ? <Text style={styles.emptyText}>Load drivers to inspect dispatch blockers.</Text> : null}

      {drivers ? (
        <>
          <Text style={styles.summaryText}>
            Eligible: {eligibleCount} | Blocked: {blockedCount}
          </Text>

          {items.length === 0 ? <Text style={styles.emptyText}>No drivers returned.</Text> : null}

          {items.slice(0, 6).map((driver) => (
            <View key={driver.id} style={styles.driverItem}>
              <Text style={styles.driverTitle}>
                {driver.name || driver.email} · {driver.dispatch_eligible ? 'Eligible' : 'Blocked'}
              </Text>
              <Text>{driver.email}</Text>
              <Text>Carrier company: {driver.carrier_company?.name || 'Unassigned'}</Text>
              {driver.dispatch_missing_document_types.length ? (
                <Text style={styles.warningText}>
                  Missing: {driver.dispatch_missing_document_types.map(formatReason).join(', ')}
                </Text>
              ) : (
                <Text style={styles.readyText}>All dispatch compliance checks are satisfied.</Text>
              )}
            </View>
          ))}
        </>
      ) : null}
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
  summaryText: {
    color: '#374151',
    fontWeight: '600',
  },
  emptyText: {
    color: '#6b7280',
  },
  driverItem: {
    borderTopWidth: 1,
    borderColor: '#e5e7eb',
    paddingTop: 8,
    gap: 3,
  },
  driverTitle: {
    fontWeight: '700',
    color: '#111827',
  },
  warningText: {
    color: '#92400e',
    fontWeight: '600',
  },
  readyText: {
    color: '#166534',
    fontWeight: '600',
  },
});
