import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import type { RequestCommunicationLog } from '../api/client';

type RequestCommunicationPanelProps = {
  communications?: RequestCommunicationLog[];
  audience: 'customer' | 'admin';
};

function formatLabel(value: string | null | undefined) {
  return (value || 'unknown').replace(/_/g, ' ');
}

export function RequestCommunicationPanel(props: RequestCommunicationPanelProps) {
  const { communications, audience } = props;
  const items = communications || [];

  return (
    <View style={styles.card}>
      <Text style={styles.title}>Communication Log</Text>
      <Text style={styles.subtitle}>
        {audience === 'admin'
          ? 'Track invoice emails, calls, and manual follow-ups on this request.'
          : 'Visible updates shared by the operator about booking and billing.'}
      </Text>

      {items.length === 0 ? (
        <Text style={styles.emptyText}>
          {audience === 'admin'
            ? 'No communication entries logged yet.'
            : 'No customer-visible communication updates yet.'}
        </Text>
      ) : null}

      {items.slice(0, 6).map((item) => (
        <View key={item.id} style={styles.item}>
          <Text style={styles.itemTitle}>
            {formatLabel(item.direction)} · {formatLabel(item.channel)}
          </Text>
          {item.subject ? <Text>Subject: {item.subject}</Text> : null}
          <Text>{item.message}</Text>
          {item.outcome ? <Text>Outcome: {item.outcome}</Text> : null}
          {audience === 'admin' ? (
            <Text>
              Customer visible: {item.customer_visible ? 'yes' : 'no'}
            </Text>
          ) : null}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    marginTop: 8,
    padding: 10,
    borderRadius: 8,
    backgroundColor: '#f8fafc',
    borderWidth: 1,
    borderColor: '#cbd5e1',
    gap: 4,
  },
  title: {
    fontSize: 14,
    fontWeight: '700',
    color: '#0f172a',
  },
  subtitle: {
    color: '#475569',
  },
  emptyText: {
    color: '#64748b',
  },
  item: {
    borderTopWidth: 1,
    borderColor: '#e2e8f0',
    paddingTop: 8,
    gap: 2,
  },
  itemTitle: {
    fontWeight: '700',
    color: '#1e293b',
    textTransform: 'capitalize',
  },
});
