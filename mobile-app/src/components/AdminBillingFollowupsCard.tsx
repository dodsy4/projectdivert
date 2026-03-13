import React, { useEffect, useState } from 'react';
import { Button, StyleSheet, Text, View } from 'react-native';
import type { AdminBillingFollowupsResponse } from '../api/client';
import { Field } from './Field';

type AdminBillingFollowupsCardProps = {
  report: AdminBillingFollowupsResponse | null;
  isLoading: boolean;
  onRefresh: (params?: {
    search?: string;
    dueOnly?: boolean;
    reminderAfterHours?: number;
    repeatHours?: number;
  }) => void;
  onRunMaintenance: (params?: {
    search?: string;
    reminderAfterHours?: number;
    repeatHours?: number;
    dryRun?: boolean;
    logReminders?: boolean;
  }) => void | Promise<unknown>;
  onInspectRequest: (requestId: number) => void;
};

function formatLabel(value: string) {
  return value.replace(/_/g, ' ');
}

export function AdminBillingFollowupsCard(props: AdminBillingFollowupsCardProps) {
  const { report, isLoading, onRefresh, onRunMaintenance, onInspectRequest } = props;
  const [search, setSearch] = useState('');
  const [reminderAfterHours, setReminderAfterHours] = useState('72');
  const [repeatHours, setRepeatHours] = useState('72');

  useEffect(() => {
    if (!report) {
      return;
    }
    setSearch(report.filters.search || '');
    setReminderAfterHours(String(report.filters.reminder_after_hours || 72));
    setRepeatHours(String(report.filters.repeat_hours || 72));
  }, [report]);

  const parsedReminderAfterHours = Number(reminderAfterHours);
  const parsedRepeatHours = Number(repeatHours);

  const refresh = () =>
    onRefresh({
      search,
      dueOnly: true,
      reminderAfterHours: Number.isFinite(parsedReminderAfterHours) ? parsedReminderAfterHours : 72,
      repeatHours: Number.isFinite(parsedRepeatHours) ? parsedRepeatHours : 72,
    });

  const runMaintenance = (dryRun: boolean) =>
    onRunMaintenance({
      search,
      reminderAfterHours: Number.isFinite(parsedReminderAfterHours) ? parsedReminderAfterHours : 72,
      repeatHours: Number.isFinite(parsedRepeatHours) ? parsedRepeatHours : 72,
      dryRun,
      logReminders: true,
    });

  return (
    <View style={styles.card}>
      <Text style={styles.title}>Billing Follow-ups</Text>
      <Text style={styles.helper}>
        Track invoice-sent requests that now need a customer reminder.
      </Text>

      <Field
        label="Search"
        value={search}
        onChangeText={setSearch}
        placeholder="invoice ref, customer email"
        autoCapitalize="none"
      />
      <Field
        label="Reminder after hours"
        value={reminderAfterHours}
        onChangeText={setReminderAfterHours}
        keyboardType="number-pad"
      />
      <Field
        label="Repeat reminder after hours"
        value={repeatHours}
        onChangeText={setRepeatHours}
        keyboardType="number-pad"
      />

      <Button
        title={isLoading ? 'Refreshing...' : 'Refresh follow-ups'}
        onPress={refresh}
        disabled={isLoading}
      />
      <Button
        title={isLoading ? 'Running dry-run...' : 'Dry-run reminder maintenance'}
        onPress={() => runMaintenance(true)}
        disabled={isLoading}
      />
      <Button
        title={isLoading ? 'Logging reminders...' : 'Log due reminders now'}
        onPress={() => runMaintenance(false)}
        disabled={isLoading}
      />

      {!report ? <Text style={styles.emptyText}>Load billing follow-up reporting.</Text> : null}

      {report ? (
        <>
          <Text style={styles.summaryText}>
            Due now: {report.summary.due_now_count} | Invoice-sent candidates: {report.summary.invoice_sent_candidates}
          </Text>
          <Text style={styles.summaryText}>
            Oldest due: {report.summary.oldest_due_hours}h | Oldest invoice age: {report.summary.oldest_invoice_age_hours}h
          </Text>

          {report.items.length === 0 ? (
            <Text style={styles.emptyText}>No invoice follow-ups are due with the current thresholds.</Text>
          ) : null}

          {report.items.slice(0, 6).map((item) => (
            <View key={item.request.id} style={styles.item}>
              <Text style={styles.itemTitle}>
                Request #{item.request.id} · {item.request.requester_name || item.request.requester_email}
              </Text>
              <Text>Reference: {item.request.billing_workflow?.reference || 'None'}</Text>
              <Text>Status: {formatLabel(item.request.status || 'unknown')}</Text>
              <Text>Invoice age: {item.followup.invoice_age_hours}h</Text>
              <Text>Due reason: {formatLabel(item.followup.due_reason || 'invoice_age_exceeded')}</Text>
              <Text>
                Last reminder: {item.followup.hours_since_last_reminder ?? 'never'}{typeof item.followup.hours_since_last_reminder === 'number' ? 'h ago' : ''}
              </Text>
              <Text>
                Last customer touch: {item.followup.hours_since_last_customer_touch ?? 'never'}{typeof item.followup.hours_since_last_customer_touch === 'number' ? 'h ago' : ''}
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
  title: {
    fontSize: 16,
    fontWeight: '700',
  },
  helper: {
    color: '#6b7280',
  },
  summaryText: {
    color: '#374151',
    fontWeight: '600',
  },
  emptyText: {
    color: '#6b7280',
  },
  item: {
    borderTopWidth: 1,
    borderColor: '#e5e7eb',
    paddingTop: 8,
    gap: 4,
  },
  itemTitle: {
    fontWeight: '700',
    color: '#111827',
  },
});
