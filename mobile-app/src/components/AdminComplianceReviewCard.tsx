import React from 'react';
import { Button, StyleSheet, Text, View } from 'react-native';
import type { AdminComplianceReviewQueueResponse } from '../api/client';

type AdminComplianceReviewCardProps = {
  queue: AdminComplianceReviewQueueResponse | null;
  isLoading: boolean;
  onRefresh: () => void;
  onReview: (requestId: number, documentId: number, status: 'verified' | 'rejected') => void;
};

function formatDocumentLabel(documentType: string) {
  return documentType.replace(/_/g, ' ').replace(/\b\w/g, (match) => match.toUpperCase());
}

export function AdminComplianceReviewCard(props: AdminComplianceReviewCardProps) {
  const { queue, isLoading, onRefresh, onReview } = props;

  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>Compliance Review Queue</Text>
      <Button
        title={isLoading ? 'Refreshing...' : 'Refresh review queue'}
        onPress={onRefresh}
        disabled={isLoading}
      />

      {!queue ? <Text style={styles.emptyText}>Load the queue to review pending evidence.</Text> : null}

      {queue ? (
        <>
          <Text style={styles.summaryText}>
            Pending items: {queue.pagination.total} | Returned: {queue.pagination.returned}
          </Text>

          {queue.items.length === 0 ? (
            <Text style={styles.emptyText}>No compliance documents need review right now.</Text>
          ) : null}

          {queue.items.slice(0, 5).map((item) => {
            if (!item.request) {
              return null;
            }
            return (
              <View key={item.document.id} style={styles.queueItem}>
                <Text style={styles.queueTitle}>
                  Request #{item.request.id} · {formatDocumentLabel(item.document.document_type)}
                </Text>
                <Text>Status: {item.document.status}</Text>
                <Text numberOfLines={1}>File: {item.document.file_url}</Text>
                <View style={styles.actionRow}>
                  <Button
                    title="Verify"
                    onPress={() => onReview(item.request!.id, item.document.id, 'verified')}
                    disabled={isLoading}
                  />
                  <Button
                    title="Reject"
                    onPress={() => onReview(item.request!.id, item.document.id, 'rejected')}
                    disabled={isLoading}
                  />
                </View>
              </View>
            );
          })}
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
  cardTitle: {
    fontSize: 16,
    fontWeight: '700',
  },
  summaryText: {
    color: '#374151',
    fontWeight: '600',
  },
  emptyText: {
    color: '#6b7280',
  },
  queueItem: {
    borderTopWidth: 1,
    borderColor: '#e5e7eb',
    paddingTop: 8,
    gap: 4,
  },
  queueTitle: {
    fontWeight: '700',
    color: '#111827',
  },
  actionRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 4,
  },
});
