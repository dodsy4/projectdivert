import React, { useMemo } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import type { WasteRequestDetails } from '../api/client';

type BillingCommunicationPanelProps = {
  details: WasteRequestDetails | null;
  audience: 'customer' | 'admin';
};

type BillingCommunicationCopy = {
  title: string;
  summary: string;
  nextAction: string;
  outboundMessage?: string;
};

function formatState(value: string | null | undefined) {
  return (value || 'pending_offline_invoice').replace(/_/g, ' ');
}

function buildCustomerCopy(details: WasteRequestDetails | null): BillingCommunicationCopy {
  const workflow = details?.request.billing_workflow;
  const state = workflow?.state || 'pending_offline_invoice';
  const reference = workflow?.reference;

  switch (state) {
    case 'invoice_sent':
      return {
        title: 'Invoice Sent',
        summary: reference
          ? `Your booking has been invoiced offline under reference ${reference}.`
          : 'Your booking has been invoiced offline.',
        nextAction: 'Use the invoice details shared outside the app to settle payment or reply to the operator if anything looks wrong.',
      };
    case 'paid_offline':
      return {
        title: 'Payment Received',
        summary: 'Offline payment has been recorded for this request.',
        nextAction: 'Keep your request ID and invoice reference for reconciliation or support questions.',
      };
    case 'payout_recorded':
      return {
        title: 'Booking Closed Financially',
        summary: 'The booking has been closed out in the operator’s offline billing workflow.',
        nextAction: 'No further payment action is expected in the app.',
      };
    case 'cancelled':
      return {
        title: 'Billing Cancelled',
        summary: 'This request is cancelled and no in-app payment will be taken.',
        nextAction: 'If you received any invoice externally, contact the operator to confirm it has been voided.',
      };
    default:
      return {
        title: 'Awaiting Offline Invoice',
        summary: 'Your request is being handled operationally, and billing will be arranged outside the app.',
        nextAction: 'Wait for booking confirmation and invoice details from the operator.',
      };
  }
}

function buildAdminCopy(details: WasteRequestDetails | null): BillingCommunicationCopy {
  const workflow = details?.request.billing_workflow;
  const state = workflow?.state || 'pending_offline_invoice';
  const reference = workflow?.reference;
  const requesterName = details?.request.requester_name || 'the customer';

  switch (state) {
    case 'invoice_sent':
      return {
        title: 'Customer Follow-Up',
        summary: reference
          ? `Invoice ${reference} has been recorded.`
          : 'An offline invoice has been recorded.',
        nextAction: 'Confirm receipt and payment window with the customer, then move the request to paid offline once settlement lands.',
        outboundMessage: `Hi ${requesterName}, your collection booking has been invoiced offline${reference ? ` under reference ${reference}` : ''}. Please use the invoice details sent separately to complete payment.`,
      };
    case 'paid_offline':
      return {
        title: 'Payout Follow-Up',
        summary: 'Customer payment is recorded offline.',
        nextAction: 'Reconcile the carrier or driver payout and update the request once payout is logged.',
        outboundMessage: `Payment for request #${details?.request.id || ''} has been received offline. Next step is reconciling carrier payout outside the app.`,
      };
    case 'payout_recorded':
      return {
        title: 'Finance Workflow Complete',
        summary: 'Invoice and payout have both been tracked outside the app.',
        nextAction: 'No further billing action is required unless support raises a dispute or correction.',
        outboundMessage: `Offline billing workflow for request #${details?.request.id || ''} is complete.`,
      };
    case 'cancelled':
      return {
        title: 'Cancellation Reconciliation',
        summary: 'The offline billing workflow is marked cancelled.',
        nextAction: 'Ensure any invoice or payout draft has been voided outside the app and keep the cancellation note attached to the request.',
        outboundMessage: `Request #${details?.request.id || ''} is cancelled. Any external invoice or payout should be voided in the finance workflow.`,
      };
    default:
      return {
        title: 'Invoice Still Needed',
        summary: `Billing is still in ${formatState(state)}.`,
        nextAction: 'Once booking/service is confirmed, send the customer invoice outside the app and record the reference here.',
        outboundMessage: `Hi ${requesterName}, your booking is confirmed operationally. Billing for this launch is handled offline, and we will send invoice details separately.`,
      };
  }
}

export function BillingCommunicationPanel(props: BillingCommunicationPanelProps) {
  const { details, audience } = props;

  const billingMode = details?.billing?.mode || 'offline';
  const copy = useMemo(() => {
    return audience === 'admin' ? buildAdminCopy(details) : buildCustomerCopy(details);
  }, [audience, details]);

  if (billingMode !== 'offline') {
    return null;
  }

  return (
    <View style={styles.card}>
      <Text style={styles.title}>{copy.title}</Text>
      <Text style={styles.summary}>{copy.summary}</Text>
      <Text style={styles.nextAction}>Next: {copy.nextAction}</Text>
      {copy.outboundMessage ? (
        <View style={styles.messageBlock}>
          <Text style={styles.messageLabel}>Suggested update</Text>
          <Text style={styles.messageText}>{copy.outboundMessage}</Text>
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
    backgroundColor: '#eef2ff',
    borderWidth: 1,
    borderColor: '#b9c4ff',
    gap: 4,
  },
  title: {
    fontSize: 14,
    fontWeight: '700',
    color: '#243b7a',
  },
  summary: {
    color: '#2f468a',
  },
  nextAction: {
    color: '#1e3a8a',
    fontWeight: '600',
  },
  messageBlock: {
    marginTop: 4,
    padding: 8,
    borderRadius: 8,
    backgroundColor: '#ffffff',
    borderWidth: 1,
    borderColor: '#dbe3ff',
    gap: 4,
  },
  messageLabel: {
    fontSize: 12,
    fontWeight: '700',
    color: '#4b5563',
    textTransform: 'uppercase',
  },
  messageText: {
    color: '#1f2937',
  },
});
