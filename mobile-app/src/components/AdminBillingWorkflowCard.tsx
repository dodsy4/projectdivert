import React, { useEffect, useState } from 'react';
import { Button, Pressable, StyleSheet, Text, View } from 'react-native';
import type { BillingWorkflowState, WasteRequestDetails } from '../api/client';
import { Field } from './Field';

const billingStates: BillingWorkflowState[] = [
  'pending_offline_invoice',
  'invoice_sent',
  'paid_offline',
  'payout_recorded',
  'cancelled',
];

type AdminBillingWorkflowCardProps = {
  details: WasteRequestDetails | null;
  isLoading: boolean;
  onSave: (requestId: number, payload: { state: string; reference?: string; notes?: string }) => void;
};

function labelForState(state: string) {
  return state.replace(/_/g, ' ');
}

export function AdminBillingWorkflowCard(props: AdminBillingWorkflowCardProps) {
  const { details, isLoading, onSave } = props;
  const [state, setState] = useState<BillingWorkflowState>('pending_offline_invoice');
  const [reference, setReference] = useState('');
  const [notes, setNotes] = useState('');

  useEffect(() => {
    const workflow = details?.request.billing_workflow;
    setState((workflow?.state as BillingWorkflowState) || 'pending_offline_invoice');
    setReference(workflow?.reference || '');
    setNotes(workflow?.notes || '');
  }, [details?.request.billing_workflow, details?.request.id]);

  if (!details) {
    return null;
  }

  return (
    <View style={styles.card}>
      <Text style={styles.title}>Admin Billing Workflow</Text>
      <Text>Request #{details.request.id}</Text>
      <View style={styles.stateRow}>
        {billingStates.map((option) => {
          const selected = state === option;
          return (
            <Pressable
              key={option}
              style={[styles.stateChip, selected ? styles.stateChipSelected : undefined]}
              onPress={() => setState(option)}
              disabled={isLoading}
            >
              <Text style={[styles.stateChipText, selected ? styles.stateChipTextSelected : undefined]}>
                {labelForState(option)}
              </Text>
            </Pressable>
          );
        })}
      </View>
      <Field label="Invoice / payout reference" value={reference} onChangeText={setReference} />
      <Field label="Billing notes" value={notes} onChangeText={setNotes} multiline />
      <Button
        title={isLoading ? 'Saving...' : 'Save billing workflow'}
        onPress={() =>
          onSave(details.request.id, {
            state,
            reference: reference.trim() || undefined,
            notes: notes.trim() || undefined,
          })
        }
        disabled={isLoading}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    marginTop: 8,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#d8d8d8',
    backgroundColor: '#ffffff',
    padding: 12,
    gap: 8,
  },
  title: {
    fontSize: 16,
    fontWeight: '700',
  },
  stateRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  stateChip: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#cccccc',
    backgroundColor: '#efefef',
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  stateChipSelected: {
    borderColor: '#1d4d1a',
    backgroundColor: '#e2f2df',
  },
  stateChipText: {
    fontSize: 12,
    color: '#2f2f2f',
    textTransform: 'capitalize',
  },
  stateChipTextSelected: {
    color: '#1d4d1a',
    fontWeight: '700',
  },
});
