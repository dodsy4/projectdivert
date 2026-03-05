import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import type { WasteRequestDetails } from '../api/client';

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
      {details.latest_location ? (
        <Text>
          Latest location: {details.latest_location.latitude},{' '}
          {details.latest_location.longitude}
        </Text>
      ) : (
        <Text>Latest location: none yet</Text>
      )}
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
