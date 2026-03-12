import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import type { BillingSummary, RequestFinancials } from '../api/client';

type BillingStatusPanelProps = {
  billing?: BillingSummary;
  financials?: RequestFinancials;
};

function formatMinor(amountMinor: number | undefined) {
  const amount = Number(amountMinor || 0) / 100;
  return `GBP ${amount.toFixed(2)}`;
}

export function BillingStatusPanel({ billing, financials }: BillingStatusPanelProps) {
  if (!billing && !financials) {
    return null;
  }

  const mode = billing?.mode || 'offline';
  const customerMessage =
    billing?.customer_message ||
    (mode === 'offline'
      ? 'Billing is arranged offline after booking confirmation.'
      : 'Payment is handled in app.');

  return (
    <View style={styles.card}>
      <Text style={styles.title}>Billing</Text>
      <Text>Mode: {mode === 'offline' ? 'Offline invoicing' : 'In-app payments'}</Text>
      <Text>{customerMessage}</Text>
      {billing?.actions_disabled?.length ? (
        <Text style={styles.helper}>
          Disabled actions: {billing.actions_disabled.join(', ')}
        </Text>
      ) : null}
      {financials ? (
        <View style={styles.totals}>
          <Text>Charged: {formatMinor(financials.totals.charged_minor)}</Text>
          <Text>Refunded: {formatMinor(financials.totals.refunded_minor)}</Text>
          <Text>Paid out: {formatMinor(financials.totals.paid_out_minor)}</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    marginTop: 8,
    padding: 10,
    borderRadius: 8,
    backgroundColor: '#f7f3e9',
    borderWidth: 1,
    borderColor: '#e0c98f',
    gap: 4,
  },
  title: {
    fontSize: 14,
    fontWeight: '700',
  },
  helper: {
    color: '#6b5a2b',
  },
  totals: {
    marginTop: 4,
    gap: 2,
  },
});
