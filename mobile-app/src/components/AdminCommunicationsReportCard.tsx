import React, { useEffect, useState } from 'react';
import { Button, Pressable, StyleSheet, Text, View } from 'react-native';
import type { AdminCommunicationsReportResponse } from '../api/client';
import { Field } from './Field';

const directions = ['all', 'outbound', 'inbound', 'internal'] as const;
const channels = ['all', 'email', 'phone', 'sms', 'manual', 'other'] as const;

type AdminCommunicationsReportCardProps = {
  report: AdminCommunicationsReportResponse | null;
  isLoading: boolean;
  onRefresh: (params?: { state?: string; direction?: string; channel?: string; search?: string }) => void;
  onInspectRequest: (requestId: number) => void;
};

function formatLabel(value: string) {
  return value.replace(/_/g, ' ');
}

export function AdminCommunicationsReportCard(props: AdminCommunicationsReportCardProps) {
  const { report, isLoading, onRefresh, onInspectRequest } = props;
  const [direction, setDirection] = useState('all');
  const [channel, setChannel] = useState('all');
  const [search, setSearch] = useState('');

  useEffect(() => {
    if (!report) {
      return;
    }
    setDirection(report.filters.direction || 'all');
    setChannel(report.filters.channel || 'all');
    setSearch(report.filters.search || '');
  }, [report]);

  return (
    <View style={styles.card}>
      <Text style={styles.title}>Communications Report</Text>

      <View style={styles.filterRow}>
        {directions.map((option) => {
          const selected = direction === option;
          return (
            <Pressable
              key={option}
              onPress={() => setDirection(option)}
              style={[styles.chip, selected ? styles.chipSelected : undefined]}
            >
              <Text style={selected ? styles.chipTextSelected : styles.chipText}>{formatLabel(option)}</Text>
            </Pressable>
          );
        })}
      </View>

      <View style={styles.filterRow}>
        {channels.map((option) => {
          const selected = channel === option;
          return (
            <Pressable
              key={option}
              onPress={() => setChannel(option)}
              style={[styles.chip, selected ? styles.chipSelected : undefined]}
            >
              <Text style={selected ? styles.chipTextSelected : styles.chipText}>{formatLabel(option)}</Text>
            </Pressable>
          );
        })}
      </View>

      <Field
        label="Search"
        value={search}
        onChangeText={setSearch}
        placeholder="invoice ref, subject, email"
        autoCapitalize="none"
      />

      <Button
        title={isLoading ? 'Refreshing...' : 'Apply report filters'}
        onPress={() => onRefresh({ direction, channel, search, state: 'all' })}
        disabled={isLoading}
      />

      {!report ? <Text style={styles.emptyText}>Load communications reporting.</Text> : null}

      {report ? (
        <>
          <Text style={styles.summaryText}>
            Entries: {report.pagination.total} | Returned: {report.pagination.returned}
          </Text>
          <Text style={styles.summaryText}>
            Directions: {Object.entries(report.summary.direction_counts).map(([key, count]) => `${formatLabel(key)}=${count}`).join(' · ') || 'none'}
          </Text>
          {report.items.length === 0 ? <Text style={styles.emptyText}>No communication entries match the filters.</Text> : null}
          {report.items.slice(0, 6).map((item) => (
            <View key={item.communication.id} style={styles.item}>
              <Text style={styles.itemTitle}>
                Request #{item.request?.id || item.communication.waste_removal_request_id} · {formatLabel(item.communication.direction)} · {formatLabel(item.communication.channel)}
              </Text>
              {item.communication.subject ? <Text>Subject: {item.communication.subject}</Text> : null}
              <Text numberOfLines={2}>{item.communication.message}</Text>
              <Text>Customer visible: {item.communication.customer_visible ? 'yes' : 'no'}</Text>
              <Button
                title="View request"
                onPress={() => onInspectRequest(item.request?.id || item.communication.waste_removal_request_id)}
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
  filterRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  chip: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#d1d5db',
    backgroundColor: '#ffffff',
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  chipSelected: {
    backgroundColor: '#111827',
    borderColor: '#111827',
  },
  chipText: {
    color: '#374151',
    textTransform: 'capitalize',
  },
  chipTextSelected: {
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
  item: {
    borderTopWidth: 1,
    borderColor: '#e5e7eb',
    paddingTop: 8,
    gap: 4,
  },
  itemTitle: {
    fontWeight: '700',
    color: '#111827',
    textTransform: 'capitalize',
  },
});
