import React from 'react';
import { ActivityIndicator, Button, StyleSheet, Text, View } from 'react-native';
import type { CreateWasteRequestResponse, WasteRequestDetails } from '../../api/client';
import { AdminBillingWorkflowCard } from '../../components/AdminBillingWorkflowCard';
import { AdminCommunicationLogCard } from '../../components/AdminCommunicationLogCard';
import { BillingCommunicationPanel } from '../../components/BillingCommunicationPanel';
import { Field } from '../../components/Field';
import { OfflineBillingChecklistPanel } from '../../components/OfflineBillingChecklistPanel';
import { RequestDetailsPanel } from '../../components/RequestDetailsPanel';

type RequestStatusScreenProps = {
  customerRequestId: string;
  setCustomerRequestId: (value: string) => void;
  onRefreshNow: () => void;
  isLoading: boolean;
  hasTrackedRequest: boolean;
  isPolling: boolean;
  isRealtimeConnected: boolean;
  isFallbackPolling: boolean;
  created: CreateWasteRequestResponse | null;
  relevantRequestDetails: WasteRequestDetails | null;
  audience?: 'customer' | 'admin';
  onUpdateBillingWorkflow?: (
    requestId: number,
    payload: { state: string; reference?: string; notes?: string },
  ) => void;
  onCreateCommunicationLog?: (
    requestId: number,
    payload: {
      direction: string;
      channel: string;
      subject?: string;
      message: string;
      outcome?: string;
      contact_name?: string;
      contact_email?: string;
      contact_phone?: string;
      customer_visible?: boolean;
    },
  ) => void;
};

export function RequestStatusScreen(props: RequestStatusScreenProps) {
  const {
    customerRequestId,
    setCustomerRequestId,
    onRefreshNow,
    isLoading,
    hasTrackedRequest,
    isPolling,
    isRealtimeConnected,
    isFallbackPolling,
    created,
    relevantRequestDetails,
    audience = 'customer',
    onUpdateBillingWorkflow,
    onCreateCommunicationLog,
  } = props;

  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>Request Status</Text>
      <Field
        label="Request ID"
        value={customerRequestId}
        onChangeText={setCustomerRequestId}
        keyboardType="number-pad"
      />
      <Button
        title={isLoading ? 'Refreshing...' : 'Refresh request'}
        onPress={onRefreshNow}
        disabled={isLoading || !hasTrackedRequest}
      />
      <View style={styles.pollRow}>
        {isPolling ? <ActivityIndicator size="small" /> : null}
        <Text>
          {!hasTrackedRequest
            ? 'Enter a request ID to start realtime tracking'
            : isRealtimeConnected
              ? 'Live stream connected'
              : isFallbackPolling
                ? 'Realtime unavailable, using polling fallback'
                : 'Connecting live stream'}
        </Text>
      </View>

      {created ? (
        <View style={styles.resultBlock}>
          <Text style={styles.blockTitle}>Latest Submission</Text>
          <Text>Request ID: {created.request.id}</Text>
          <Text>Status: {created.request.status}</Text>
          <Text>
            Offers sent: {created.dispatch?.offers_created ?? 0} | Notifications:{' '}
            {created.dispatch?.provider_notifications_sent ?? 0}
          </Text>
          <Text>Billing: arranged offline until in-app payments are enabled</Text>
        </View>
      ) : null}

      {relevantRequestDetails ? <RequestDetailsPanel details={relevantRequestDetails} audience={audience} /> : null}
      <BillingCommunicationPanel details={relevantRequestDetails} audience={audience} />
      {audience === 'admin' && onUpdateBillingWorkflow ? (
        <AdminBillingWorkflowCard
          details={relevantRequestDetails}
          isLoading={isLoading}
          onSave={onUpdateBillingWorkflow}
        />
      ) : null}
      {audience === 'admin' && onCreateCommunicationLog ? (
        <AdminCommunicationLogCard
          details={relevantRequestDetails}
          isLoading={isLoading}
          onSave={onCreateCommunicationLog}
        />
      ) : null}
      <OfflineBillingChecklistPanel details={relevantRequestDetails} audience={audience} />
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
  pollRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 8,
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
});
