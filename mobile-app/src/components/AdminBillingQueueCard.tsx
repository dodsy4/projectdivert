import React, { useEffect, useState } from 'react';
import { Button, Pressable, StyleSheet, Text, View } from 'react-native';
import type { AdminBillingQueueResponse, BillingWorkflowState } from '../api/client';
import { Field } from './Field';

const billingStates: Array<BillingWorkflowState | 'all'> = [
  'all',
  'pending_offline_invoice',
  'invoice_sent',
  'paid_offline',
  'payout_recorded',
  'cancelled',
];

type AdminBillingQueueCardProps = {
  queue: AdminBillingQueueResponse | null;
  isLoading: boolean;
  onRefresh: (params?: {
    state?: string;
    reference?: string;
    search?: string;
    requestStatus?: string;
  }) => void;
  onInspectRequest: (requestId: number) => void;
};

function formatStateLabel(value: string) {
  return value.replace(/_/g, ' ');
}

function nextActionForState(state: string) {
  switch (state) {
    case 'invoice_sent':
      return 'Await customer settlement';
    case 'paid_offline':
      return 'Record carrier payout';
    case 'payout_recorded':
      return 'Closed';
    case 'cancelled':
      return 'Void external finance records';
    default:
      return 'Issue invoice';
  }
}

export function AdminBillingQueueCard(props: AdminBillingQueueCardProps) {
  const { queue, isLoading, onRefresh, onInspectRequest } = props;
  const [state, setState] = useState<string>('all');
  const [reference, setReference] = useState('');
  const [search, setSearch] = useState('');

  useEffect(() => {
    if (!queue) {
      return;
    }
    setState(queue.filters.state || 'all');
    setReference(queue.filters.reference || '');
    setSearch(queue.filters.search || '');
  }, [queue]);

  const applyFilters = () => {
    onRefresh({
      state,
      reference,
      search,
      requestStatus: 'all',
    });
  };

  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>Offline Billing Queue</Text>

      <View style={styles.filterWrap}>
        {billingStates.map((option) => {
          const selected = state === option;
          return (
            <Pressable
              key={option}
              onPress={() => setState(option)}
              style={[styles.filterChip, selected ? styles.filterChipSelected : undefined]}
            >
              <Text style={selected ? styles.filterChipTextSelected : styles.filterChipText}>
                {option === 'all' ? 'all' : formatStateLabel(option)}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <Field
        label="Billing reference"
        value={reference}
        onChangeText={setReference}
        placeholder="INV-1001"
        autoCapitalize="characters"
      />
      <Field
        label="Search"
        value={search}
        onChangeText={setSearch}
        placeholder="customer email or postcode"
        autoCapitalize="none"
      />

      <Button
        title={isLoading ? 'Refreshing...' : 'Apply filters'}
        onPress={applyFilters}
        disabled={isLoading}
      />

      {!queue ? <Text style={styles.emptyText}>Load the queue to track invoices and payouts.</Text> : null}

      {queue ? (
        <>
          <Text style={styles.summaryText}>
            Matching requests: {queue.pagination.total} | Returned: {queue.pagination.returned}
          </Text>
          <Text style={styles.summaryText}>
            State counts: {Object.entries(queue.summary.state_counts).map(([key, count]) => `${formatStateLabel(key)}=${count}`).join(' · ') || 'none'}
          </Text>

          {queue.items.length === 0 ? (
            <Text style={styles.emptyText}>No requests match the current billing filters.</Text>
          ) : null}

          {queue.items.slice(0, 6).map((item) => (
            <View key={item.request.id} style={styles.queueItem}>
              <Text style={styles.queueTitle}>
                Request #{item.request.id} · {formatStateLabel(item.request.billing_workflow?.state || 'pending_offline_invoice')}
              </Text>
              <Text>{item.request.requester_name} · {item.request.requester_email}</Text>
              <Text>Status: {item.request.status}</Text>
              <Text>Reference: {item.request.billing_workflow?.reference || 'None'}</Text>
              <Text>Next action: {nextActionForState(item.request.billing_workflow?.state || 'pending_offline_invoice')}</Text>
              <Text>
                Totals: charged {item.financials.totals.charged_minor} · refunded {item.financials.totals.refunded_minor} · payout {item.financials.totals.paid_out_minor}
              </Text>
              <Button
                title="View request"
                onPress={() => onInspectRequest(item.request.id)}
                disabled={isLoading}
              />
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
  filterWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  filterChip: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#d1d5db',
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: '#ffffff',
  },
  filterChipSelected: {
    backgroundColor: '#111827',
    borderColor: '#111827',
  },
  filterChipText: {
    color: '#374151',
    textTransform: 'capitalize',
  },
  filterChipTextSelected: {
    color: '#ffffff',
    textTransform: 'capitalize',
  },
  summaryText: {
    color: '#374151',
    fontWeight: '600',
  },
  emptyText: {
    color: '#6b7280',
  },
  queueItem: {
    borderTopWidth: 1,
    borderColor: '#e5e7eb',
    paddingTop: 8,
    gap: 4,
  },
  queueTitle: {
    fontWeight: '700',
    color: '#111827',
    textTransform: 'capitalize',
  },
});
