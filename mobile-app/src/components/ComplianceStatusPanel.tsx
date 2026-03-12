import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import type { ComplianceSummary } from '../api/client';

type ComplianceStatusPanelProps = {
  summary: ComplianceSummary | null | undefined;
};

function formatDocumentLabel(documentType: string) {
  return documentType.replace(/_/g, ' ').replace(/\b\w/g, (match) => match.toUpperCase());
}

export function ComplianceStatusPanel({ summary }: ComplianceStatusPanelProps) {
  if (!summary) {
    return null;
  }

  const requiredTypes = summary.required_document_types || [];
  const completionRequiredTypes = summary.completion_required_document_types || [];

  return (
    <View style={styles.section}>
      <Text style={styles.title}>Compliance</Text>
      <Text style={styles.statusText}>
        Review ready: {summary.is_ready ? 'Yes' : 'No'} | Completion ready:{' '}
        {summary.can_complete_request ? 'Yes' : 'No'}
      </Text>

      {requiredTypes.map((documentType) => {
        const entry = summary.by_type?.[documentType];
        const isCompletionRequired = completionRequiredTypes.includes(documentType);
        return (
          <View key={documentType} style={styles.row}>
            <Text style={styles.label}>
              {formatDocumentLabel(documentType)}
              {isCompletionRequired ? ' (required to complete)' : ''}
            </Text>
            <Text style={styles.value}>
              {entry?.verified
                ? 'Verified'
                : entry?.present
                  ? `Pending (${entry.latest_status || 'submitted'})`
                  : 'Missing'}
            </Text>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  section: {
    borderTopWidth: 1,
    borderColor: '#e5e5e5',
    marginTop: 8,
    paddingTop: 8,
    gap: 6,
  },
  title: {
    fontSize: 14,
    fontWeight: '700',
  },
  statusText: {
    color: '#374151',
    fontWeight: '600',
  },
  row: {
    gap: 2,
  },
  label: {
    color: '#111827',
    fontWeight: '600',
  },
  value: {
    color: '#4b5563',
  },
});
