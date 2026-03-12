import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import type { WasteRequestDetails } from '../api/client';
import { BillingStatusPanel } from './BillingStatusPanel';
import { ComplianceStatusPanel } from './ComplianceStatusPanel';

type RequestDetailsPanelProps = {
  details: WasteRequestDetails;
};

export function RequestDetailsPanel({ details }: RequestDetailsPanelProps) {
  return (
    <View style={styles.resultBlock}>
      <Text style={styles.blockTitle}>Live Request Snapshot</Text>
      <Text>Request ID: {details.request.id}</Text>
      <Text>Status: {details.request.status}</Text>
      <Text>
        Provider:{' '}
        {details.match?.provider_name ||
          details.dispatch?.accepted_offer?.provider_name ||
          'Pending'}
      </Text>
      <Text>
        Assigned driver user ID: {details.request.assigned_driver_user_id ?? 'Unassigned'}
      </Text>
      <Text>
        Dispatch: {details.dispatch?.offers_sent ?? 0} offers,{' '}
        {details.dispatch?.offers_open ?? 0} open
      </Text>
      <Text>
        Offline billing state: {details.request.billing_workflow?.state?.replace(/_/g, ' ') || 'pending offline invoice'}
      </Text>
      {details.request.billing_workflow?.reference ? (
        <Text>Billing reference: {details.request.billing_workflow.reference}</Text>
      ) : null}
      {details.latest_location ? (
        <Text>
          Latest location: {details.latest_location.latitude},{' '}
          {details.latest_location.longitude}
        </Text>
      ) : (
        <Text>Latest location: none yet</Text>
      )}
      <BillingStatusPanel billing={details.billing} financials={details.financials} />
      <ComplianceStatusPanel summary={details.compliance?.summary} />
    </View>
  );
}

const styles = StyleSheet.create({
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
