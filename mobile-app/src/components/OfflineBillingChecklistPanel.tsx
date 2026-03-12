import React, { useMemo } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import type { WasteRequestDetails } from '../api/client';

type OfflineBillingChecklistPanelProps = {
  details: WasteRequestDetails | null;
  audience: 'customer' | 'admin';
};

type ChecklistState = {
  title: string;
  intro: string;
  steps: string[];
};

function buildCustomerChecklist(details: WasteRequestDetails | null): ChecklistState {
  const status = (details?.request.status || 'pending_match').toLowerCase();
  const assigned = details?.request.assigned_driver_user_id != null;

  switch (status) {
    case 'completed':
      return {
        title: 'Booking Completed',
        intro: 'Collection is complete. Billing remains offline for this launch.',
        steps: [
          'Expect the invoice or billing confirmation from the operator separately.',
          'Keep your request ID available for invoice matching or support questions.',
          'If anything looks wrong, contact support before manual payment is settled.',
        ],
      };
    case 'collected':
    case 'arrived':
    case 'en_route':
      return {
        title: 'Collection In Progress',
        intro: 'Your collection is active and billing will be handled separately from the app.',
        steps: [
          assigned ? 'A driver has been assigned and is progressing the job.' : 'Ops is still coordinating the live collection.',
          'No card charge will happen in app.',
          'Invoice and payment instructions will be sent outside the app after service confirmation.',
        ],
      };
    case 'cancelled':
      return {
        title: 'Booking Cancelled',
        intro: 'This request is no longer active.',
        steps: [
          'No in-app payment will be taken.',
          'If any manual invoice was already issued, ops must reconcile it outside the app.',
        ],
      };
    default:
      return {
        title: 'Awaiting Booking Confirmation',
        intro: 'Your request has been received. This launch uses offline invoicing.',
        steps: [
          'Ops will confirm the booking and assign a driver.',
          'No in-app card payment will be requested.',
          'Billing will be arranged separately after the booking is confirmed.',
        ],
      };
  }
}

function buildAdminChecklist(details: WasteRequestDetails | null): ChecklistState {
  const status = (details?.request.status || 'pending_match').toLowerCase();
  const chargedMinor = details?.financials?.totals?.charged_minor || 0;
  const refundedMinor = details?.financials?.totals?.refunded_minor || 0;
  const paidOutMinor = details?.financials?.totals?.paid_out_minor || 0;

  const financialState =
    chargedMinor > 0 || refundedMinor > 0 || paidOutMinor > 0
      ? `Recorded totals in app: charged ${chargedMinor}, refunded ${refundedMinor}, paid out ${paidOutMinor}.`
      : 'No in-app money movement is recorded for this request.';

  switch (status) {
    case 'completed':
      return {
        title: 'Offline Billing Close-Out',
        intro: `${financialState} Complete the commercial close-out outside the app.`,
        steps: [
          'Issue or reconcile the customer invoice manually.',
          'Record carrier or driver payout in your finance workflow, not in the app.',
          'Store external invoice and payout references alongside the request ID.',
        ],
      };
    case 'cancelled':
      return {
        title: 'Cancelled Request Handling',
        intro: `${financialState} No automated refund path exists in this launch mode.`,
        steps: [
          'Cancel any external invoice or payment request manually.',
          'Record the cancellation outcome against the request ID.',
        ],
      };
    default:
      return {
        title: 'Offline Invoicing Ops Checklist',
        intro: `${financialState} The request is operationally active but financially offline.`,
        steps: [
          'Confirm booking and driver assignment operationally.',
          'Do not attempt to charge, refund, or pay out through the app while payments are disabled.',
          'Send invoice and settle carrier payout through the offline finance process after service confirmation.',
        ],
      };
  }
}

export function OfflineBillingChecklistPanel(props: OfflineBillingChecklistPanelProps) {
  const { details, audience } = props;
  const billingMode = details?.billing?.mode || 'offline';

  const checklist = useMemo(() => {
    return audience === 'admin'
      ? buildAdminChecklist(details)
      : buildCustomerChecklist(details);
  }, [audience, details]);

  if (billingMode !== 'offline') {
    return null;
  }

  return (
    <View style={styles.card}>
      <Text style={styles.title}>{checklist.title}</Text>
      <Text style={styles.intro}>{checklist.intro}</Text>
      {checklist.steps.map((step, index) => (
        <Text key={`${index}-${step}`} style={styles.step}>
          {index + 1}. {step}
        </Text>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    marginTop: 8,
    padding: 10,
    borderRadius: 8,
    backgroundColor: '#eef6ec',
    borderWidth: 1,
    borderColor: '#9fc59a',
    gap: 4,
  },
  title: {
    fontSize: 14,
    fontWeight: '700',
    color: '#1d4d1a',
  },
  intro: {
    color: '#2d5e28',
  },
  step: {
    color: '#2d5e28',
  },
});
